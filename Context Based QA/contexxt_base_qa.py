# -*- coding: utf-8 -*-
"""Contexxt-base QA.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1ru3YwnERlYC6PuqLKeg0e0eqL15-MdbW

# Data and Library installation
"""

!git clone "https://github.com/wasiahmad/PolicyQA.git"

!pip install pytorch-accelerated datasets transformers evaluate tqdm torchmetrics

"""# Library"""

from torch import nn
import os
import torch
import numpy as np
import pandas as pd
import pickle, time
import re, os, string, typing, gc, json
import torch.nn.functional as F
import spacy
from sklearn.model_selection import train_test_split
from collections import Counter
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, DefaultDataCollator, TrainingArguments, Trainer
from torch.utils.data import DataLoader, Dataset
# from pytorch_accelerated import Trainer
import datasets
import matplotlib.pyplot as plt
import random
import collections
import evaluate
import torchmetrics
from torchmetrics.text import BLEUScore, SacreBLEUScore
from torchmetrics.text.rouge import ROUGEScore
from tqdm import tqdm

"""#Config"""

train_json_path = "/content/PolicyQA/data/train.json"
test_json_path = "/content/PolicyQA/data/test.json"


trained_checkpoint_bert = "kaporter/bert-base-uncased-finetuned-squad"
trained_checkpoint_t5 = "sjrhuschlee/flan-t5-base-squad2"
trained_checkpoint_bart = "sjrhuschlee/bart-base-squad2"

epochs = 10
max_answer_length = 100
n_best = 20
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# device = torch.device('cpu')
print(f'Available device: {device}')

"""# Data Loading"""

def load_json(path):
    '''
    Loads the JSON file of the Squad dataset.
    Returns the json object of the dataset.
    '''
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("Length of data: ", len(data['data']))
    print("Data Keys: ", data['data'][0].keys())
    print("Title: ", data['data'][0]['title'])

    return data

train_data = load_json(train_json_path)
test_data = load_json(test_json_path)

def parse_data(data:dict)->list:
    '''
    Parses the JSON file of Squad dataset by looping through the
    keys and values and returns a list of dictionaries with
    context, query and label triplets being the keys of each dict.
    '''
    data = data['data']
    qa_list = []

    for paragraphs in data:

        for para in paragraphs['paragraphs']:
            context = para['context']

            for qa in para['qas']:

                id = qa['id']
                question = qa['question']

                for ans in qa['answers']:
                    answer = ans['text']
                    ans_start = ans['answer_start']
                    ans_end = ans_start + len(answer)

                    qa_dict = {}
                    qa_dict['id'] = id
                    qa_dict['context'] = context
                    qa_dict['question'] = question
                    # qa_dict['label'] = [ans_start, ans_end]
                    qa_dict['answer_start'] = ans['answer_start']
                    qa_dict['answer_end'] = ans_end

                    qa_dict['answer'] = answer
                    qa_list.append(qa_dict)


    return qa_list

train_list = parse_data(train_data)
test_list = parse_data(test_data)

print('Train list len: ',len(train_list))
print('Test list len:', len(test_list))

# converting the lists into dataframes
train_df = pd.DataFrame(train_list)
df_train, df_valid = train_test_split(train_df, test_size=0.1, random_state=42)
print(f"Train dataset size: {len(df_train)} | Val Dataset size: {len(df_valid)}")

test_df = pd.DataFrame(test_list)

# Assuming train_df is your pandas DataFrame
dataset_train = datasets.Dataset.from_pandas(df_train)
dataset_valid = datasets.Dataset.from_pandas(df_valid)
dataset_test = datasets.Dataset.from_pandas(test_df)

train_sample = dataset_train.select([i for i in range(2000)])
val_sample = dataset_valid.select([i for i in range(500)])
test_sample = dataset_test.select([i for i in range(100)])

"""#BLUE and ROUGE Implementation"""

class ROUGE():
    def __init__(self):
        self.rouge = ROUGEScore()

    def compute(self, predictions, references):
        rouge1_fmeasure = 0
        rouge1_precision = 0
        rouge1_recall = 0

        rouge2_fmeasure = 0
        rouge2_precision = 0
        rouge2_recall = 0

        rougeL_fmeasure = 0
        rougeL_precision = 0
        rougeL_recall = 0

        for prediction, reference in zip(predictions, references):
            pred = prediction['prediction_text']
            target = reference['answers']['text'][0]
            result = self.rouge(pred, target)

            rouge1_fmeasure += result['rouge1_fmeasure']
            rouge1_precision += result['rouge1_precision']
            rouge1_recall += result['rouge1_recall']

            rouge2_fmeasure += result['rouge2_fmeasure']
            rouge2_precision += result['rouge2_precision']
            rouge2_recall += result['rouge2_recall']

            rougeL_fmeasure += result['rougeL_fmeasure']
            rougeL_precision += result['rougeL_precision']
            rougeL_recall += result['rougeL_recall']

        n = len(predictions)
        rouge1_fmeasure /= n
        rouge1_precision /= n
        rouge1_recall /= n

        rouge2_fmeasure /= n
        rouge2_precision /= n
        rouge2_recall /= n

        rougeL_fmeasure /= n
        rougeL_precision /= n
        rougeL_recall /= n

        return {
            'rouge1_fmeasure': rouge1_fmeasure,
            'rouge1_precision': rouge1_precision,
            'rouge1_recall': rouge1_recall,
            'rouge2_fmeasure': rouge2_fmeasure,
            'rouge2_precision': rouge2_precision,
            'rouge2_recall': rouge2_recall,
            'rougeL_fmeasure': rougeL_fmeasure,
            'rougeL_precision': rougeL_precision,
            'rougeL_recall': rougeL_recall,
        }

class BLEU():
    def __init__(self, bleu, n_gram=4, smooth=False, weights=None):
        # super().__init__()
        self.bleu_score = bleu
        self.scare_bleu = SacreBLEUScore()

    def compute(self, predictions, references):
        bleu_scores = []  # Store individual scores
        scare_bleu_scores = []
        for prediction, reference in zip(predictions, references):
            pred = prediction['prediction_text']
            target = reference['answers']['text']
            bleu_scores.append(self.bleu_score([pred], [target]))
            scare_bleu_scores.append(self.scare_bleu([pred], [target]))

        average_bleu = sum(bleu_scores) / len(bleu_scores)
        average_sacre = sum(scare_bleu_scores) / len(scare_bleu_scores)

        return {'bleu': average_bleu, 'sacre_bleu_score': average_sacre}

def compute_metrics(start_logits, end_logits, features, examples, metrics):
    example_to_features = collections.defaultdict(list)
    # print(examples.columns.tolist())
    for idx, feature in enumerate(features):
        example_to_features[feature["id"]].append(idx)

    # print(example_to_features)
    predicted_answers = []
    for example in tqdm(examples):
        # print("Srting is:",example)

        # break
        example_id = example["id"]
        context = example["context"]
        answers = []

        # print(example)

        # Loop through all features associated with that example
        for feature_index in example_to_features[example_id]:
            start_logit = start_logits[feature_index]
            end_logit = end_logits[feature_index]
            offsets = features[feature_index]["offset_mapping"]

            start_indexes = np.argsort(start_logit)[-1 : -n_best - 1 : -1].tolist()
            end_indexes = np.argsort(end_logit)[-1 : -n_best - 1 : -1].tolist()
            for start_index in start_indexes:
                for end_index in end_indexes:
                    # Skip answers that are not fully in the context
                    if offsets[start_index] is None or offsets[end_index] is None:
                        continue
                    # Skip answers with a length that is either < 0 or > max_answer_length
                    if (
                        end_index < start_index
                        or end_index - start_index + 1 > max_answer_length
                    ):
                        continue

                    answer = {
                        "text": context[offsets[start_index][0] : offsets[end_index][1]],
                        "logit_score": start_logit[start_index] + end_logit[end_index],
                    }
                    answers.append(answer)

        # Select the answer with the best score
        if len(answers) > 0:
            best_answer = max(answers, key=lambda x: x["logit_score"])
            predicted_answers.append(
                {"id": example_id, "prediction_text": best_answer["text"]}
            )
        else:
            predicted_answers.append({"id": example_id, "prediction_text": ""})

    # print(predicted_answers)
    theoretical_answers = [{'id': ex['id'], 'answers': {"text": [ex['answer']], 'answer_start': [ex['answer_start']]}} for ex in examples]

    print(predicted_answers[0])
    print(theoretical_answers[0])

    for name, metric in metrics.items():
        print(metric.compute(predictions=predicted_answers, references=theoretical_answers))

"""# Bert-Base

##Bert Data Creation
"""

def train_data_preprocess_bert(examples):

    """
    generate start and end indexes of answer in context
    """

    def find_context_start_end_index(sequence_ids):
        """
        returns the token index in whih context starts and ends
        """
        token_idx = 0
        while sequence_ids[token_idx] != 1:  #means its special tokens or tokens of queston
            token_idx += 1                   # loop only break when context starts in tokens
        context_start_idx = token_idx

        while sequence_ids[token_idx] == 1:
            token_idx += 1
        context_end_idx = token_idx - 1
        return context_start_idx,context_end_idx


    questions = [q.strip() for q in examples["question"]]
    context = examples["context"]
    answers = examples["answer"]

    answer_start = examples['answer_start']
    answer_end = examples['answer_end']
    # labels = examples['label']

    inputs = tokenizer_bert(
        questions,
        context,
        max_length=512,
        truncation="only_second",
        stride=128,
        return_overflowing_tokens=True,  #returns id of base context
        return_offsets_mapping=True,  # returns (start_index,end_index) of each token
        padding="max_length"
    )


    start_positions = []
    end_positions = []


    for i,mapping_idx_pairs in enumerate(inputs['offset_mapping']):
        context_idx = inputs['overflow_to_sample_mapping'][i]

        # from main context
        answer = answers[context_idx]
        # print(labels)
        # print(labels[0][0])
        answer_start_char_idx = answer_start[i]
        # print(answer_start_char_idx)
        # answer_end_char_idx = answer_start_char_idx + len(answer)
        answer_end_char_idx = answer_end[i]
        # print(answer_end_char_idx)

        # break


        # now we have to find it in sub contexts
        tokens = inputs['input_ids'][i]
        sequence_ids = inputs.sequence_ids(i)

        # finding the context start and end indexes wrt sub context tokens
        context_start_idx,context_end_idx = find_context_start_end_index(sequence_ids)

        #if the answer is not fully inside context label it as (0,0)
        # starting and end index of charecter of full context text
        context_start_char_index = mapping_idx_pairs[context_start_idx][0]
        context_end_char_index = mapping_idx_pairs[context_end_idx][1]


        #If the answer is not fully inside the context, label is (0, 0)
        if (context_start_char_index > answer_start_char_idx) or (
            context_end_char_index < answer_end_char_idx):
            start_positions.append(0)
            end_positions.append(0)

        else:

            # else its start and end token positions
            # here idx indicates index of token
            idx = context_start_idx
            while idx <= context_end_idx and mapping_idx_pairs[idx][0] <= answer_start_char_idx:
                idx += 1
            start_positions.append(idx - 1)


            idx = context_end_idx
            while idx >= context_start_idx and mapping_idx_pairs[idx][1] > answer_end_char_idx:
                idx -= 1
            end_positions.append(idx + 1)

    inputs["start_positions"] = start_positions
    inputs["end_positions"] = end_positions
    return inputs

def preprocess_validation_bert(examples):
    """
    preprocessing validation data
    """
    questions = [q.strip() for q in examples["question"]]
    inputs = tokenizer_bert(
        questions,
        examples["context"],
        max_length=512,
        truncation="only_second",
        stride=128,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        padding="max_length",
    )

    sample_map = inputs.pop("overflow_to_sample_mapping")

    base_ids = []

    for i in range(len(inputs["input_ids"])):

        # take the base id (ie in cases of overflow happens we get base id)
        base_context_idx = sample_map[i]
        base_ids.append(examples["id"][base_context_idx])

        # sequence id indicates the input. 0 for first input and 1 for second input
        # and None for special tokens by default
        sequence_ids = inputs.sequence_ids(i)
        offset = inputs["offset_mapping"][i]
        # for Question tokens provide offset_mapping as None
        inputs["offset_mapping"][i] = [
            o if sequence_ids[k] == 1 else None for k, o in enumerate(offset)
        ]

    inputs["base_id"] = base_ids
    return inputs

tokenized_train_data_bert = train_sample.map(train_data_preprocess_bert, batched=True)
tokenized_val_data_bert = val_sample.map(preprocess_validation_bert, batched=True)
tokenized_test_data_bert = test_sample.map(preprocess_validation_bert, batched=True)

"""## Bert Model"""

# tokenizer = AutoTokenizer.from_pretrained("ainize/klue-bert-base-mrc")
tokenizer_bert = AutoTokenizer.from_pretrained(trained_checkpoint_bert)
model_bert = AutoModelForQuestionAnswering.from_pretrained(trained_checkpoint_bert)
model_bert = model_bert.to(device)

"""##Bert-base training & prediction and evalation"""

def train_model(model, model_name, epochs, tokenized_train_data, tokenized_val_data, tokenizer):
    data_collator = DefaultDataCollator()
    training_args = TrainingArguments(
        output_dir=f"/results/{model_name}-policyQA",
        evaluation_strategy="epoch",
        learning_rate=2e-5,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=16,
        num_train_epochs=epochs,
        weight_decay=0.01,
        push_to_hub=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train_data,
        eval_dataset=tokenized_val_data,
        tokenizer=tokenizer,
        data_collator=data_collator,
    )

    trainer.train()

    return trainer

trainer = train_model(model=model_bert, model_name='bert', epochs=epochs, tokenized_train_data=tokenized_train_data_bert, tokenized_val_data=tokenized_val_data_bert, tokenizer=tokenizer_bert)

predicted_answers = []
predictions, _, _ = trainer.predict(tokenized_test_data_bert)
start_logits, end_logits = predictions

BLUE_Score = BLEUScore()
metrics = {'exact_match': evaluate.load("squad"), 'rouge' : ROUGE()}
compute_metrics(start_logits, end_logits, tokenized_test_data_bert, test_sample, metrics)

"""# Bert-Large Training"""

bert_large_model_name = "Graphcore/bert-large-uncased-squad"
model_bert_large = AutoModelForQuestionAnswering.from_pretrained(bert_large_model_name)
model_bert_large = model_bert_large.to(device)

"""# T5-base

##T5 model loading
"""

tokenizer_t5 = AutoTokenizer.from_pretrained(trained_checkpoint_t5)
model_t5 = AutoModelForQuestionAnswering.from_pretrained(trained_checkpoint_t5)
model_t5 = model_t5.to(device)

"""##T5 Data Creation"""

def train_data_preprocess_t5(examples):

    """
    generate start and end indexes of answer in context
    """

    def find_context_start_end_index(sequence_ids):
        """
        returns the token index in whih context starts and ends
        """
        token_idx = 0
        while sequence_ids[token_idx] != 1:  #means its special tokens or tokens of queston
            token_idx += 1                   # loop only break when context starts in tokens
        context_start_idx = token_idx

        while sequence_ids[token_idx] == 1:
            token_idx += 1
        context_end_idx = token_idx - 1
        return context_start_idx,context_end_idx


    questions = [q.strip() for q in examples["question"]]
    context = examples["context"]
    answers = examples["answer"]

    answer_start = examples['answer_start']
    answer_end = examples['answer_end']
    # labels = examples['label']

    inputs = tokenizer_t5(
        questions,
        context,
        max_length=512,
        truncation="only_second",
        stride=128,
        return_overflowing_tokens=True,  #returns id of base context
        return_offsets_mapping=True,  # returns (start_index,end_index) of each token
        padding="max_length"
    )


    start_positions = []
    end_positions = []


    for i,mapping_idx_pairs in enumerate(inputs['offset_mapping']):
        context_idx = inputs['overflow_to_sample_mapping'][i]

        # from main context
        answer = answers[context_idx]
        # print(labels)
        # print(labels[0][0])
        answer_start_char_idx = answer_start[i]
        # print(answer_start_char_idx)
        # answer_end_char_idx = answer_start_char_idx + len(answer)
        answer_end_char_idx = answer_end[i]
        # print(answer_end_char_idx)

        # break


        # now we have to find it in sub contexts
        tokens = inputs['input_ids'][i]
        sequence_ids = inputs.sequence_ids(i)

        # finding the context start and end indexes wrt sub context tokens
        context_start_idx,context_end_idx = find_context_start_end_index(sequence_ids)

        #if the answer is not fully inside context label it as (0,0)
        # starting and end index of charecter of full context text
        context_start_char_index = mapping_idx_pairs[context_start_idx][0]
        context_end_char_index = mapping_idx_pairs[context_end_idx][1]


        #If the answer is not fully inside the context, label is (0, 0)
        if (context_start_char_index > answer_start_char_idx) or (
            context_end_char_index < answer_end_char_idx):
            start_positions.append(0)
            end_positions.append(0)

        else:

            # else its start and end token positions
            # here idx indicates index of token
            idx = context_start_idx
            while idx <= context_end_idx and mapping_idx_pairs[idx][0] <= answer_start_char_idx:
                idx += 1
            start_positions.append(idx - 1)


            idx = context_end_idx
            while idx >= context_start_idx and mapping_idx_pairs[idx][1] > answer_end_char_idx:
                idx -= 1
            end_positions.append(idx + 1)

    inputs["start_positions"] = start_positions
    inputs["end_positions"] = end_positions
    return inputs

def preprocess_validation_t5(examples):
    """
    preprocessing validation data
    """
    questions = [q.strip() for q in examples["question"]]
    inputs = tokenizer_t5(
        questions,
        examples["context"],
        max_length=512,
        truncation="only_second",
        stride=128,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        padding="max_length",
    )

    sample_map = inputs.pop("overflow_to_sample_mapping")

    base_ids = []

    for i in range(len(inputs["input_ids"])):

        # take the base id (ie in cases of overflow happens we get base id)
        base_context_idx = sample_map[i]
        base_ids.append(examples["id"][base_context_idx])

        # sequence id indicates the input. 0 for first input and 1 for second input
        # and None for special tokens by default
        sequence_ids = inputs.sequence_ids(i)
        offset = inputs["offset_mapping"][i]
        # for Question tokens provide offset_mapping as None
        inputs["offset_mapping"][i] = [
            o if sequence_ids[k] == 1 else None for k, o in enumerate(offset)
        ]

    inputs["base_id"] = base_ids
    return inputs

tokenized_train_data_t5 = train_sample.map(train_data_preprocess_t5, batched=True)
tokenized_val_data_t5 = val_sample.map(preprocess_validation_t5, batched=True)
tokenized_test_data_t5 = test_sample.map(preprocess_validation_t5, batched=True)

"""##T5-base training & prediction and evalation"""

trainer_t5 = train_model(model=model_t5, model_name='t5', epochs=epochs, tokenized_train_data=tokenized_train_data_t5, tokenized_val_data=tokenized_val_data_t5, tokenizer=tokenizer_t5)

predicted_answers = []
predictions, _, _ = trainer_t5.predict(tokenized_test_data_t5)
start_logits, end_logits = predictions

BLUE_Score = BLEUScore()
metrics = {'exact_match': evaluate.load("squad"), 'rouge' : ROUGE()}
compute_metrics(start_logits, end_logits, tokenized_test_data_t5, test_sample, metrics)

"""# Bart-Base

##Bart Model Loading
"""

model_bart = AutoModelForQuestionAnswering.from_pretrained(trained_checkpoint_bart)
tokenizer_bart = AutoTokenizer.from_pretrained(trained_checkpoint_bart)
model_bart = model_bart.to(device)

"""##Bart data creation"""

def train_data_preprocess_bart(examples):

    """
    generate start and end indexes of answer in context
    """

    def find_context_start_end_index(sequence_ids):
        """
        returns the token index in whih context starts and ends
        """
        token_idx = 0
        while sequence_ids[token_idx] != 1:  #means its special tokens or tokens of queston
            token_idx += 1                   # loop only break when context starts in tokens
        context_start_idx = token_idx

        while sequence_ids[token_idx] == 1:
            token_idx += 1
        context_end_idx = token_idx - 1
        return context_start_idx,context_end_idx


    questions = [q.strip() for q in examples["question"]]
    context = examples["context"]
    answers = examples["answer"]

    answer_start = examples['answer_start']
    answer_end = examples['answer_end']
    # labels = examples['label']

    inputs = tokenizer_bart(
        questions,
        context,
        max_length=512,
        truncation="only_second",
        stride=128,
        return_overflowing_tokens=True,  #returns id of base context
        return_offsets_mapping=True,  # returns (start_index,end_index) of each token
        padding="max_length"
    )


    start_positions = []
    end_positions = []


    for i,mapping_idx_pairs in enumerate(inputs['offset_mapping']):
        context_idx = inputs['overflow_to_sample_mapping'][i]

        # from main context
        answer = answers[context_idx]
        # print(labels)
        # print(labels[0][0])
        answer_start_char_idx = answer_start[i]
        # print(answer_start_char_idx)
        # answer_end_char_idx = answer_start_char_idx + len(answer)
        answer_end_char_idx = answer_end[i]
        # print(answer_end_char_idx)

        # break


        # now we have to find it in sub contexts
        tokens = inputs['input_ids'][i]
        sequence_ids = inputs.sequence_ids(i)

        # finding the context start and end indexes wrt sub context tokens
        context_start_idx,context_end_idx = find_context_start_end_index(sequence_ids)

        #if the answer is not fully inside context label it as (0,0)
        # starting and end index of charecter of full context text
        context_start_char_index = mapping_idx_pairs[context_start_idx][0]
        context_end_char_index = mapping_idx_pairs[context_end_idx][1]


        #If the answer is not fully inside the context, label is (0, 0)
        if (context_start_char_index > answer_start_char_idx) or (
            context_end_char_index < answer_end_char_idx):
            start_positions.append(0)
            end_positions.append(0)

        else:

            # else its start and end token positions
            # here idx indicates index of token
            idx = context_start_idx
            while idx <= context_end_idx and mapping_idx_pairs[idx][0] <= answer_start_char_idx:
                idx += 1
            start_positions.append(idx - 1)


            idx = context_end_idx
            while idx >= context_start_idx and mapping_idx_pairs[idx][1] > answer_end_char_idx:
                idx -= 1
            end_positions.append(idx + 1)

    inputs["start_positions"] = start_positions
    inputs["end_positions"] = end_positions
    return inputs

def preprocess_validation_bart(examples):
    """
    preprocessing validation data
    """
    questions = [q.strip() for q in examples["question"]]
    inputs = tokenizer_bart(
        questions,
        examples["context"],
        max_length=512,
        truncation="only_second",
        stride=128,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        padding="max_length",
    )

    sample_map = inputs.pop("overflow_to_sample_mapping")

    base_ids = []

    for i in range(len(inputs["input_ids"])):

        # take the base id (ie in cases of overflow happens we get base id)
        base_context_idx = sample_map[i]
        base_ids.append(examples["id"][base_context_idx])

        # sequence id indicates the input. 0 for first input and 1 for second input
        # and None for special tokens by default
        sequence_ids = inputs.sequence_ids(i)
        offset = inputs["offset_mapping"][i]
        # for Question tokens provide offset_mapping as None
        inputs["offset_mapping"][i] = [
            o if sequence_ids[k] == 1 else None for k, o in enumerate(offset)
        ]

    inputs["base_id"] = base_ids
    return inputs

tokenized_train_data_bart = train_sample.map(train_data_preprocess_bart, batched=True)
tokenized_val_data_bart = val_sample.map(preprocess_validation_bart, batched=True)
tokenized_test_data_bart = test_sample.map(preprocess_validation_bart, batched=True)

"""##Bart-base training & prediction and evaluation"""

trainer_bart = train_model(model=model_bart, model_name='bart', epochs=epochs, tokenized_train_data=tokenized_train_data_bart, tokenized_val_data=tokenized_val_data_bart, tokenizer=tokenizer_t5)

predicted_answers = []
predictions, _, _ = trainer_bart.predict(tokenized_test_data_bart)
start_logits, end_logits = predictions

BLUE_Score = BLEUScore()
metrics = {'exact_match': evaluate.load("squad"), 'rouge' : ROUGE()}
compute_metrics(start_logits, end_logits, tokenized_test_data_bart, test_sample, metrics)