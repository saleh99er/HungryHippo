import os
os.environ['USER_AGENT'] = 'MyCustomAgent/1.0' # For Langchain
import bs4
from langchain import hub
from langchain_chroma import Chroma
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate
from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore
import shutil
import logging
import datetime

from html_content_fetch import setup_web_request_cache, extract_additional_sources, process_webpage
from utils import get_current_datetime, EVENT_RAG_PROMPT

logging.basicConfig(level=logging.INFO)

LOCAL_FUN_WEB_CSV_PATH = os.path.join(os.pardir, "data", "local_fun_web.csv")
VECTOR_STORE_PERSIST_DIR = os.path.join(os.pardir, "data", "vector_store")
OLLAMA_ADDR = "0.0.0.0:11434"
EMBEDDING_MODEL = "nomic-embed-text:latest"
LLM_MODEL = "llama3.2"
LLM_TEMP = 0.2

# Extract local fun events

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

class HungryHippo:
    def __init__(self, llm_hosting_address=OLLAMA_ADDR, prompt_template=EVENT_RAG_PROMPT):
        self.llm_hosting_address = llm_hosting_address
        self.prompt_template = prompt_template
        self.embedding_model = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=self.llm_hosting_address) 
        self.vector_store = self.index_setup()
        self.retriever = self.vector_store.as_retriever()
        self.retriever = self.retriever.with_config({"search_kwargs": {"k": 10}})
        self.llm = ChatOllama(model=LLM_MODEL, temperature=LLM_TEMP, base_url=self.llm_hosting_address)
        self.memory = ConversationBufferMemory(return_messages=True)
        self.create_rag_chain() # stored in self.rag_chain
        self.wipe_vector_store(reinitialize=True) if self.evaluate_index_stale() else None

    def index_setup(self) -> Chroma:
        if not os.path.exists(VECTOR_STORE_PERSIST_DIR):
            os.makedirs(VECTOR_STORE_PERSIST_DIR, exist_ok=True)
            os.chmod(VECTOR_STORE_PERSIST_DIR, 0o755)
        if os.listdir(VECTOR_STORE_PERSIST_DIR):
            vectorstore = Chroma(persist_directory=VECTOR_STORE_PERSIST_DIR, embedding_function=self.embedding_model)
            temp_store = vectorstore.get()
            print("Loaded vector store dict length: ", len(temp_store))
            print("Vector store: ", temp_store)
        else:
            setup_web_request_cache()
            web_sources = extract_additional_sources(LOCAL_FUN_WEB_CSV_PATH)
            # loader = WebBaseLoader(
            #     web_paths=(web_sources),
            # )
            # docs = loader.load()
            # text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            # splits = text_splitter.split_documents(docs)
            # vectorstore = Chroma.from_documents(documents=splits, embedding=self.embedding_model, persist_directory=VECTOR_STORE_PERSIST_DIR)
            docs = []
            for web_source in web_sources:
                [docs.append(doc) for doc in process_webpage(web_source)]
            print(type(docs[0]))
            print(len(docs))
            vectorstore = Chroma.from_documents(documents=docs, embedding=self.embedding_model, persist_directory=VECTOR_STORE_PERSIST_DIR) 
        return vectorstore
    
    
    def wipe_vector_store(self, reinitialize=True) -> None:
        shutil.rmtree(VECTOR_STORE_PERSIST_DIR, ignore_errors=True)
        self.vector_store = None
        if reinitialize:
            print("Vector store reinitializing")
            self.index_setup()
            self.retriever = self.vector_store.as_retriever()
            self.retriever = self.retriever.with_config({"search_kwargs": {"k": 10}})


    def create_rag_chain(self) -> None:
        """ Assign RAG chain to Hungry Hippo instance. """
        self.rag_chain = (
        RunnableParallel(
            context=self.retriever | format_docs,
            question=RunnablePassthrough(),
            date=RunnablePassthrough() | get_current_datetime,
            history=RunnablePassthrough() | (lambda _: self.memory.load_memory_variables({})["history"])
        ) 
        | self.prompt_template.partial()
        | self.llm 
        | StrOutputParser()
        )
    
    def preprocess(self, input_dict):
        # TODO - finish implementing conditional chain so RAG and other tools won't be called if pre-processing deems it unneccessary
        pre_process_prompt = ChatPromptTemplate.from_template(
        "Given the following question and the current date, determine if the question can be answered directly or if it requires additional context retrieval. Respond with either 'DIRECT' or 'RAG'.\n\nQuestion: {question}\nCurrent Date: {date}\n\nDecision:"
        )
        chain = pre_process_prompt | self.llm | StrOutputParser()
        decision = chain.invoke(input_dict)
        return {"need_rag": decision.strip() == "RAG", **input_dict}
    
    def direct_answer(input_dict):
        # TODO - finish implementing conditional chain so RAG and other tools won't be called if pre-processing deems it unneccessary
        pass
    
    def retrieval_and_answer(self, question):
        response = self.rag_chain.invoke(question)
        self.memory.save_context({"input":question},{"output":response})
        return response

    def evaluate_index_stale(self):
        """ Evaluates True if sqllite file isn't present or older than 7 days, False otherwise """
        sqllite_file = os.path.join(VECTOR_STORE_PERSIST_DIR, 'chroma.sqlite3')
        if not os.path.exists(sqllite_file):
            return True
        else:
            creation_time = os.path.getctime(sqllite_file)
            creation_time = datetime.datetime.fromtimestamp(creation_time)
            diff = datetime.datetime.now() - creation_time
            return diff > datetime.timedelta(days=7)
    
if __name__ == "__main__":
    print(get_current_datetime())
    hungry_hippo = HungryHippo()
    print("Welcome to HungryHippo! Type 'exit' to end the conversation, 'reset' to reset the vector store.")
    while True:
        user_input = input("You: ")
        if user_input.lower().strip() == 'exit':
            print("HungryHippo: Goodbye! Have a great day.")
            break
        if user_input.lower().strip() == 'reset':
            print("HungryHippo: resetting the vector store and fetching events, one moment...")
            hungry_hippo.wipe_vector_store()
            print("HungryHippo: done with reset")
        response = hungry_hippo.retrieval_and_answer(user_input.strip())
        print("HungryHippo: ", response)
