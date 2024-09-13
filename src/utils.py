import requests
from bs4 import BeautifulSoup
import csv
import os
import requests_cache
from datetime import datetime
from langchain.prompts import PromptTemplate

EVENT_RAG_PROMPT = PromptTemplate.from_template("""
You are an assistant for finding local events named HungryHippo. Today is {date}. 
Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know. Answer the user's queries and when providing events, please provide the date (start and end), location, and source for the information.
Please only provide events in which the end date is believed to be today or later. Past events are not of interest.
Question: {question}
Context: {context}
Answer: 
"""
)

SIM_WEB_HEADER = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 (KHTML, like Gecko) Version/9.0.2 Safari/601.3.9'}
TIMEOUT = 30  # in seconds


def get_current_datetime(_=None):
    return datetime.now().strftime("%m/%d/%Y, %A, %I:%M:%S %p")

def print_if_verbose(str: str, verbose: bool = False):
    if verbose:
        print(str)


def setup_web_request_cache(verbose: bool = False):
    cache_dir = os.path.join(os.pardir, 'data', 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, 'web_cache.sqlite')
    if os.path.exists(cache_file):
        requests_cache.install_cache(cache_file, backend='sqlite')
        print_if_verbose(
            f"Using existing cache file: {cache_file}", verbose=verbose)
    else:
        requests_cache.install_cache(
            cache_file, backend='sqlite', expire_after=3600)
        print_if_verbose(
            f"Created new cache file: {cache_file}", verbose=verbose)


""" Given a URL and selector, fetch additional links of interest"""


def find_followup_links(session: requests.Session, url: str, selector: str, verbose=False):
    # proxies=PROXY, verify=False)
    response = session.get(url, timeout=TIMEOUT, headers=SIM_WEB_HEADER)
    print_if_verbose("cached? {}".format(
        getattr(response, 'from_cache', False)), verbose=verbose)
    soup = BeautifulSoup(response.content, 'html.parser')
    # urljoin(url,link['href']) for link in soup.select(selector) if url is relative link
    return [link['href'] for link in soup.select(selector)]


def extract_sources(source_csv_path, verbose=False):
    website_list = []
    session = requests.Session()
    with open(source_csv_path, 'r', newline='') as source_links_csv:
        csv_reader = csv.reader(source_links_csv)
        next(csv_reader)  # skip header row
        for row in csv_reader:
            if len(row) != 3:
                print_if_verbose("error parsing row", verbose=verbose)
                continue
            id = row[0].strip()
            website_url = row[1].strip()
            css_selector = row[2].strip()
            print_if_verbose("base url: {}".format(
                website_url), verbose=verbose)
            website_list.append(website_url)
            for follow_up_url in find_followup_links(session, website_url, css_selector, verbose=verbose):
                website_list.append(follow_up_url)
                if verbose:
                    print_if_verbose("follow up url: {}".format(
                        follow_up_url), verbose=verbose)
    return website_list


if __name__ == '__main__':
    setup_web_request_cache()

    # FOR DEBUGGING
    # test_response = test_proxy()
    # test_response = test_reg_connection()
    # print(test_response.status_code)
    # website_list = []
    # requests.get("https://www.google.com", proxies=PROXY, headers=SIM_WEB_HEADER)

    website_list = extract_sources("../data/source_links.csv", verbose=True)
    print(website_list)
