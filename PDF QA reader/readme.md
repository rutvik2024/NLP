# PDF Question Answering app using LangChain

A question-answering demo using Astra DB and LangChain, powered by Vector Search.

This project was created to work with LangChain, CassandraDB, and AstraDB to develop a PDF question-answering app.

Here I provide a PDF file as an input, which will be divided into small text chunks to create a text vector using OPENAI text embedding. This all-text vector will be stored in a NoSQL-based AstraDB powered by CassandrasDB for faster vector similarity search with text embedding. So at the end, I provide a question that will be converted into a text vector, and after I perform a similarity search with text embedding, I generate five answers. Out of which, the first is more relevant than the other 4.

## Installation

Install required libraries with the following command:

```
pip install -q cassio datasets langchain openai tiktoken 
pip install PyPDF2
```

## Set up
From AstraDB, generate a token and get an API key and DBID. Fill in the below details.

ASTRA_DB_APPLICATION_TOKEN = "Your AstraDB Token"
ASTRA_DB_ID = "Your AstraDB ID"


From openAI generate API key and add below.
OPENAI_API_KEY = "Your open AI API key"

## provide the path of  pdf file/files.

```pdfreader = PdfReader('file.pdf')```


That's it run your code :)