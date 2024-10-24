
import os
os.environ['USER_AGENT'] = 'HungryHippoDocDebug/1.0' # For Langchain
from bs4 import BeautifulSoup
from langchain import hub
from langchain_chroma import Chroma
from langchain_community.document_loaders import WebBaseLoader, BSHTMLLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_text_splitters import HTMLHeaderTextSplitter, RecursiveCharacterTextSplitter, HTMLSectionSplitter
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate
from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore
import shutil
import requests
import tempfile
import re
from langchain.schema import Document



from utils import extract_sources, setup_web_request_cache, SIM_WEB_HEADER
from filter_webpage import load_filter_rules, filter_webpage_content

LOCAL_FUN_WEB_CSV_PATH = os.path.join(os.pardir, "data", "local_fun_web.csv")
FILTER_RULES_CSV_PATH = os.path.join(os.pardir, "data", "filters.csv")
VECTOR_STORE_PERSIST_DIR = os.path.join(os.pardir, "data", "vector_store")
TMP_MISC_DIR = os.path.join(os.pardir, "data", "tmp")
TMP_HTML_DIR = os.path.join(os.pardir, "data","html")
OLLAMA_ADDR = "0.0.0.0:11434"
EMBEDDING_MODEL = "nomic-embed-text:latest"


def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def simple_docs_processing(link_txt_path):
    embedding_model = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_ADDR) 
    setup_web_request_cache()
    web_sources = extract_sources(LOCAL_FUN_WEB_CSV_PATH, verbose=False)
    #web_sources = [link_txt_path]
    loader = WebBaseLoader(web_sources)
    docs = loader.load()
    # print(docs)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200) 
    splits = text_splitter.split_documents(docs)
    [print(item) for item in splits]
    with open('chunks_debugging.txt','w') as f:
        for i,chunk in enumerate(splits):
            f.write(f"{i} " + "="*70 + "\n")
            f.write(str(chunk.page_content) + "\n")
        f.write(f"metadata " + "="*70 + "\n")
        f.write(str(splits[0].metadata))

def remove_html_tags(text):
    # Remove HTML tags
    clean_text = re.sub('<[^<]+?>', '', text)
    # Replace multiple spaces with a single space
    clean_text = re.sub('\\s+', ' ', clean_text)
    # Remove leading/trailing whitespace
    clean_text = clean_text.strip()
    return clean_text

def insert_split_markers(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for i in range(1, 7):  # h1 to h6
        for heading in soup.find_all(f'h{i}'):
            heading.insert(0, f'META_H_SPLIT_HERE_{i} ')
    return str(soup)

def custom_marker_splitter(html_content):
    # Insert markers
    marked_content = insert_split_markers(html_content)
    
    # Split content
    splits = re.split(r'(META_H_SPLIT_HERE_\d )', marked_content)
    
    # Create documents
    documents = []
    current_content = ""
    current_heading_level = "0"
    current_heading_text = ""
    
    for i, split in enumerate(splits):
        if split.startswith('META_H_SPLIT_HERE_'):
            # If there's content before this heading, add it as a document
            if current_content.strip():
                documents.append(Document(
                    page_content=re.sub(r'<[^>]+>', '', current_content.strip()),
                    metadata={
                        'heading_level': current_heading_level,
                        'heading_text': current_heading_text,
                        'index': len(documents)
                    }
                ))
            
            # Update the current heading level
            current_heading_level = split[-1]
            current_content = ""
        else:
            # Extract the heading text if present
            match = re.match(r'<h\d[^>]*>(.*?)</h\d>', split)
            if match:
                current_heading_text = match.group(1)
                # Remove the heading from the content
                split = re.sub(r'<h\d[^>]*>.*?</h\d>', '', split, count=1)
            
            current_content += split

    # Add the last document if there's remaining content
    if current_content.strip():
        documents.append(Document(
            page_content=re.sub(r'<[^>]+>', '', current_content.strip()),
            metadata={
                'heading_level': current_heading_level,
                'heading_text': current_heading_text,
                'index': len(documents)
            }
        ))
    
    return documents

def html_processing():
    embedding_model = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_ADDR) 
    setup_web_request_cache()
    filter_rules = load_filter_rules(FILTER_RULES_CSV_PATH)

    # Fetch the HTML content
    web_source = "https://www.washingtonpost.com/dc-md-va/2024/10/17/best-restaurants-georgetown-dc/"
    
    filtered_html_content = filter_webpage_content(web_source, filter_rules)

    print(filtered_html_content[:1000])
    print("="*80)
    
    with tempfile.NamedTemporaryFile(dir=TMP_HTML_DIR, mode="w", suffix=".html", delete=False) as temp_file:
        temp_file.write(filtered_html_content)
        temp_file_path = temp_file.name
    
    loader = BSHTMLLoader(temp_file_path, get_text_separator=" ")
    #docs = loader.load()
    
    # page_content = docs[0].page_content
    # print(page_content[:1000])
    # print("="*80)
    
    headers_to_split_on = [
        ("h1", "Header 1"),
        ("h2", "Header 2"),
        ("h3", "Header 3"),
        ("h4", "Header 4"),
    ]
    html_splitter = HTMLHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    docs = loader.load_and_split(text_splitter=html_splitter)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=2500,
        chunk_overlap=600
    )
    # splits = text_splitter.split_text(page_content)
    # splits = custom_marker_splitter(filtered_html_content)
    # #splits = html_splitter.split_text(filtered_html_content)
    # splits = [{'page_content': remove_html_tags(split.page_content), 'metadata':split.metadata} for split in splits]
    #[print(item) for item in splits]
    with open('chunks_debugging.txt','w') as f:
        for i,split in enumerate(docs):
            f.write(f"{i} " + "="*70 + "\n")
            f.write(split.page + "\n")
            # heading_text = split.get('metadata').get('heading_text')
            # heading_level = split.get('metadata').get('heading_level')

            # f.write(f"Heading: {heading_text} (Level {heading_level})")
        f.write(f"metadata " + "="*70 + "\n")
        # f.write(str(splits[0].metadata))

if __name__ == '__main__':
    #simple_docs_processing()
    html_processing()