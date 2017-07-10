import json, os, re, shutil, sys, time
import collections, itertools
import unittest
from IPython.display import display, HTML

# NLTK for NLP utils and corpora
import nltk

# NumPy and TensorFlow
import numpy as np
import tensorflow as tf
assert(tf.__version__.startswith("1."))

from bs4 import BeautifulSoup
import re

# utils.pretty_print_matrix uses Pandas. Configure float format here.
import pandas as pd
pd.set_option('float_format', lambda f: "{0:.04f}".format(f))

# Helper libraries
from shared_lib import utils, vocabulary, tf_embed_viz

###### Define functions 
def get_vocab2(raw):
    tokens = nltk.word_tokenize(raw) #.decode("utf8"))
    words = [w.lower() for w in tokens]
    vocab = sorted(set(words))
    sents = nltk.sent_tokenize(raw.lower())
    return vocab, sents

    
def get_vocab(filename):
    raw = open(filename).read().decode("UTF-8")
    return get_vocab2(raw)

def add_to_dict(pres_dict, president, vocab, sents):
    words = list()
    for s in sents:
        words.extend(nltk.word_tokenize(s))

    vocab_, sents_, words_ = pres_dict.get(president, (None, None, None))
    if (vocab_ == None):
        pres_dict[president] = (vocab, sents, words)
    else:
        vocab_ += vocab
        sents_ += sents
        words_.extend(words)
        pres_dict[president] = (vocab_, sents_, words_)

def print_dict(pres_dict):        
    for key in pres_dict.keys():
        vocab, sents, words = pres_dict.get(key, (None, None, None))
        print "%s: vocab count %s, sentence count %s, word count %s" % (key, len(vocab), len(sents), len(words))
        #print "Samples: ", sents[-4:]

full_name = {"Obama" : "Barack Obama", "Lincoln": "Abraham Lincoln", "Trump": "Donald J. Trump"}

#############################
def read_processed_data(dir):
    print "Processing", dir, "..."
    pres_dict = {}
    for filename in os.listdir(dir):
        arr = filename.split("_")
        president = arr[0]
    
        try:
            vocab, sents = get_vocab(dir + filename)
            add_to_dict(pres_dict, full_name[president], vocab, sents)
        except UnicodeDecodeError as err:
            print filename, ":", err

    return pres_dict

#############################
def read_unprocessed_data(pres_dict, dir):
    print "Processing", dir, "..."
    for json_file in os.listdir(dir):
        json_data=open(dir + json_file)
        data = json.load(json_data)
        json_data.close()
        attrName = 'debate' if 'Debate' in json_file else 'speeches'
        for data2 in data[attrName]:
            # data2['text'] has a lot of htmtl tags in there. We still need to parse it            
            raw = BeautifulSoup(data2['text'], "html.parser").get_text()
            # Remove []
            raw = re.sub(' \[.*?\]',' ', raw, flags=re.DOTALL)
            # Remove ()
            raw = re.sub(' \(.*?\)',' ', raw, flags=re.DOTALL)
            if (attrName == 'speeches' and 'News Conference With' not in data2['name']):
                # Cleaning up the data: eemoving the questions
                raw = re.sub('[A-Z,\s,\.]Q\..*? The President\.','\.',raw, flags=re.DOTALL)
                raw = re.sub('^[A-Z,\s]*THE PRESIDENT\.','',raw, flags=re.DOTALL)
                raw = re.sub('[A-Z,\s,\.]Q\..*?THE PRESIDENT\.','\.',raw, flags=re.DOTALL)

                vocab, sents = get_vocab2(raw)
                #arr = data2['speaker'].split(' ')
                #president = arr[len(arr)-1]
                president = data2['speaker'] 

                sents = sents[:len(sents)-10]
                #print sents[-2:]
                #print len(sents)
                add_to_dict(pres_dict, president, vocab, sents)

            ########################################################
            # TODO: extract debate data for TRUMP, OBAMA
            #elif ('OBAMA' in raw): #('TRUMP' in raw or 'OBAMA' in raw)):
            #    print data2['name'] #, raw[0:3000]

#############################
# Create train and test data set
# Number of words used by 1 president
def append_matrices(a,b):
    if (a == None):
        return b
    else:
        return np.concatenate((a, b))

def get_train_test(pres_dict, num_words_limit, batch_size=100):
    print "Max number of words:", num_words_limit

    def reshape_y(y):
        return np.reshape(y,[len(y),len(y[0])])
            
    y_train = None
    X_train = None
    y_test = None
    X_test = None
    all_words = list()
    president_int = {}

    # Set up president_int: find out how many meets the word count requirement
    for key in pres_dict.keys():
        vocab, sents, words = pres_dict.get(key, (None, None))
        if (len(words) >= num_words_limit):
            president_int[key] = None # initialize this mapping
    i = 0
    for p in president_int.keys():
        arr = [0]* len(president_int.keys())
        arr[i] = 1
        president_int[p] = arr
        i +=1
    #print president_int
        
    # Then use president_int to build y matrices
    for key in pres_dict.keys():
        vocab, sents, words = pres_dict.get(key, (None, None))
        if (len(words) >= num_words_limit):
            print "Processing data for", key            
            X = words[0:num_words_limit]
            all_words += X
            X = np.reshape(X, [len(X)/batch_size, batch_size])
            #y = (num_words_limit * [president_int[key]])
            y = reshape_y(X.shape[0] * [president_int[key]])
            #print y
            #print X.shape,y.shape
            # train = 80%, test = 20%
            train_len = int(y.shape[0] * 0.8)
            #print train_len
            ## add new rows to y_train
            y_train = append_matrices(y_train, y[:train_len])
            #print y_train.shape
                            
            X_train = append_matrices(X_train, X[:train_len])
            y_test = append_matrices(y_test, y[train_len:])
            X_test = append_matrices(X_test, X[train_len:])
        
    return president_int, vocabulary.Vocabulary(all_words), y_train, X_train, y_test, X_test

# Convert 2d matrix of words into 2d matrix of word ids
def word_matrix_2ids(vocab, word_matrix):
    # convert to 1d
    word_1d = word_matrix.flatten()
    ids = vocab.words_to_ids(word_1d)
    return np.reshape(ids, (-1, word_matrix.shape[1]))

############################
def create_train_test_data(pres_dict, num_of_words, batch_size): 
    president_int, vocab, y_train, X_train, y_test, X_test = get_train_test(pres_dict, num_of_words, batch_size)
    ###### Shuffle data?

    # Convert words to ids
    X_train = word_matrix_2ids(vocab, X_train) 
    X_test = word_matrix_2ids(vocab, X_test)
    return president_int, y_train, X_train, y_test, X_test


