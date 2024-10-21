from urllib.parse import urlparse
from bs4 import BeautifulSoup, NavigableString, Comment
import requests
from langchain.schema import Document
import re
import csv
import os

from utils import SIM_WEB_HEADER
FILTER_RULES_CSV_PATH = os.path.join(os.pardir, "data", "filters.csv")

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
    # response = requests.get(url, headers=SIM_WEB_HEADER)
    # soup = BeautifulSoup(response.text, 'html.parser')
    if domain not in filter_rules:
        print(f"No filtering rules found for domain: {domain}")

    matching_rules = filter_rules.get(domain,[])
    for element, class_name in matching_rules:
        print(element, class_name, "found: ", len(soup.find_all(element, class_=class_name)))
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
    soup = BeautifulSoup(response.content, 'html.parser')
    filter_webpage_content(url, soup, load_filter_rules(FILTER_RULES_CSV_PATH))
    
    # Remove unwanted elements (adjust as needed)
    for element in soup(element_types_to_remove):
        element.decompose()
    for comment in soup(text= lambda t: isinstance(t, Comment)):
        comment.extract()
    
    return soup

def get_text_until_next_header(element):
    """ """
    text = []
    for sibling in element.next_siblings:
        if sibling.name and sibling.name.startswith('h'):
            break
        if isinstance(sibling, NavigableString):
            text.append(sibling.strip())
        else:
            text.append(sibling.get_text(strip=True))
    return ' '.join(text)

def split_by_headers(soup):
    soup = flatten_structure(soup)
    with open("../data/tmp/debug.html", "w") as f:
        f.write(str(soup))
        # print(soup)
    content = soup.find('div',{'id':'flattened-content'}) or soup.body
    
    if not content:
        print("content not found")
        return [Document(page_content=soup.get_text(), metadata={})]
    
    headers = content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    # print("headers found: ",str(headers))
    splits = []
    
    for header in headers:
        # Get all text content until the next header, regardless of nesting
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
        print("Invalid URL")
        return []

# Usage
if __name__ == '__main__':
    exit_requested = False
    while not exit_requested:
        user_input = input("Please enter the URL of the webpage you want to analyze: ").strip()
        if 'exit' == user_input.lower():
            exit_requested = True
        else:
            documents = process_webpage(user_input)
            for doc in documents:
                print(f"Metadata: {doc.metadata}")
                print(f"Content: {doc.page_content[:1000]}...")
                print("-" * 50)
        