from urllib.parse import urlparse
from bs4 import BeautifulSoup, NavigableString, Comment, ResultSet
import requests
from langchain.schema import Document
import re
import datetime
import csv
import os
import logging
import requests_cache

logging.basicConfig(level=logging.DEBUG)

FILTER_RULES_CSV_PATH = os.path.join(os.pardir, "data", "filters.csv")
WEB_CACHE_DIR = os.path.join(os.pardir, 'data', 'web_cache')
DEBUG_HTML = os.path.join(os.pardir, "data","tmp","debug.html")
SIM_WEB_HEADER = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 (KHTML, like Gecko) Version/9.0.2 Safari/601.3.9'}
TIMEOUT = 15  # in seconds

def setup_web_request_cache():
    os.makedirs(WEB_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(WEB_CACHE_DIR, 'web_cache.sqlite')
    if os.path.exists(cache_file):
        requests_cache.install_cache(cache_file, backend='sqlite')
        logging.debug(
            f"Using existing cache file: {cache_file}")
    else:
        requests_cache.install_cache(
            cache_file, backend='sqlite', expire_after=3600)
        logging.debug(
            f"Created new cache file: {cache_file}")


def find_followup_links(session: requests.Session, url: str, selector: str):
    """ Given a URL and selector, fetch additional links of interest"""
    # proxies=PROXY, verify=False)
    response = session.get(url, timeout=TIMEOUT, headers=SIM_WEB_HEADER)
    logging.debug("cached? {}".format(
        getattr(response, 'from_cache', False)))
    soup = BeautifulSoup(response.content, 'html.parser')
    # urljoin(url,link['href']) for link in soup.select(selector) if url is relative link
    return [link['href'] for link in soup.select(selector)]


def extract_additional_sources(source_csv_path):
    website_list = []
    session = requests.Session()
    with open(source_csv_path, 'r', newline='') as source_links_csv:
        csv_reader = csv.reader(source_links_csv)
        next(csv_reader)  # skip header row
        for row in csv_reader:
            if len(row) != 3:
                logging.debug("error parsing row, expecting 3 elements per row")
                continue
            id = row[0].strip()
            website_url = row[1].strip()
            css_selector = row[2].strip()
            logging.debug("base url: {}".format(
                website_url))
            website_list.append(website_url)
            for follow_up_url in find_followup_links(session, website_url, css_selector):
                website_list.append(follow_up_url)
                logging.info("follow up url: {}".format(
                        follow_up_url))    
    return website_list


def load_filter_rules(csv_file):
    rules = {}
    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) >= 3:
                domain, element, class_name = row[0].strip(), row[1].strip(), row[2].strip()
                if domain not in rules:
                    rules[domain] = [(element, class_name)]
                else:
                    rules[domain].append((element, class_name))
    return rules


def extract_domain(url):
    parsed_url = urlparse(url)
    return parsed_url.netloc.split('.')[-2] + '.' + parsed_url.netloc.split('.')[-1]


def filter_webpage_content(url: str, soup: BeautifulSoup, filter_rules: dict):
    domain = extract_domain(url)
    if domain not in filter_rules:
        logging.debug(f"No filtering rules found for domain: {domain}")

    matching_rules = filter_rules.get(domain,[])
    for element, class_name in matching_rules:
        logging.debug(" %s %s found: %d", element, class_name, len(soup.find_all(element, class_=class_name)))
        for tag in soup.find_all(element, class_=class_name):
            tag.decompose()
    return soup


def flatten_structure(soup):
    """ Flatten HTML element hierarchy to support splitting of content by header """
    flattened = BeautifulSoup('<div id="flattened-content"></div>', 'html.parser')
    root = flattened.div
    current_header = None

    def extract_content(element):
        nonlocal current_header
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            current_header = element.name
            root.append(element.extract())
        elif isinstance(element, NavigableString) and element.strip():
            if current_header:
                root.append(element.extract())
        elif element.name == 'p':
            root.append(element.extract())
        else:
            if hasattr(element, 'children'):
                for child in element.children:
                    extract_content(child)

    # Start extraction from the body
    body = soup.body or soup
    extract_content(body)
    return flattened


def fetch_and_parse_html(url, element_types_to_remove=['script', 'style', 'nav', 'header', 'footer']):
    """ Fetch webpage from the given URL without certain element types"""
    response = requests.get(url, headers=SIM_WEB_HEADER)
    logging.debug("cached? {}".format(
        getattr(response, 'from_cache', False)))
    soup = BeautifulSoup(response.content, 'html.parser')
    filter_webpage_content(url, soup, load_filter_rules(FILTER_RULES_CSV_PATH))
    
    # Remove unwanted elements (adjust as needed)
    for element in soup(element_types_to_remove):
        element.decompose()
    for comment in soup(text= lambda t: isinstance(t, Comment)):
        comment.extract()
    return soup


def get_text_until_next_header(element):
    """ Get web element contents up until the next header """
    text = []
    for sibling in element.next_siblings:
        if sibling.name and sibling.name.startswith('h'):
            break
        if isinstance(sibling, NavigableString):
            text.append(sibling.strip())
        else:
            text.append(sibling.get_text(strip=True))
    return ' '.join(text)

def debug_header_info(header_result_set: ResultSet):
    logging.debug("Headers found ==================")
    if(len(header_result_set) == 0):
        logging.debug(" no headers found")
    for header in header_result_set:
        logging.debug("%s%s", int(header.name[1:])*"\t",header.text.strip())

def split_by_headers(soup):
    """ Given a flattened webpage, split webpage based on header elements. """
    soup = flatten_structure(soup)
    with open("../data/tmp/debug.html", "w") as f:
        f.write(str(soup))
    content = soup.find('div',{'id':'flattened-content'}) or soup.body
    if not content:
        logging.debug("content not found from webpage, possibly failure from extraction")
        return [Document(page_content=soup.get_text(), metadata={})]
    headers = content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    debug_header_info(headers)
    splits = []
    for header in headers:
        # Get all text content until the next header
        section_content = get_text_until_next_header(header)
        clean_content = re.sub(r'\s+', ' ', section_content).strip()
        splits.append(Document(
            page_content=clean_content,
            metadata={
                'header': header.get_text(strip=True),
                'level': header.name
            }
        ))
    return splits

def process_webpage(url):
    try:
        soup = fetch_and_parse_html(url)
        splits = split_by_headers(soup)
        return splits
    except requests.exceptions.MissingSchema as e:
        logging.error("Invalid URL")
        return []
    
def log_document_info(doc: Document):
    logging.info(f"Metadata: {doc.metadata}")
    content_elipsis = "..." if len(doc.page_content) > 1000 else ""
    logging.info(f"Content: {doc.page_content[:1000]}{content_elipsis}")
    logging.info("-" * 50)

# Usage
if __name__ == '__main__':
    setup_web_request_cache()
    website_list = extract_additional_sources("../data/local_fun_web.csv")
    # logging.debug(website_list)
    for website in website_list:
        docs = process_webpage(website)
        for doc in docs:
            log_document_info(doc)
    # Interactive extraction
    exit_requested = False
    while not exit_requested:
        user_input = input("Please enter the URL of the webpage you want to analyze: ").strip()
        if 'exit' == user_input.lower():
            exit_requested = True
        else:
            documents = process_webpage(user_input)
            for doc in documents:
                log_document_info(doc)

    