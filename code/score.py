from clustering import *
from preprocess import *
from embedding import *

from sklearn.metrics import pairwise_distances_argmin_min
import sys
import npmi
import argparse
import string
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import gensim
import pdb
import math
import random

NSEEDS = 5

# python3 code/score.py --clustering_algo KMeans --vocab /usr/share/dict/words --entities word2vec

def main():
    args = parse_args()

    stopwords = set(line.strip() for line in open('stopwords_en.txt'))

    vocab = create_global_vocab(args.vocab)
    train_word_to_file, train_w_to_f_mult, files = create_vocab_and_files(stopwords, args.dataset, args.preprocess, "train", vocab)
    files_num = len(files)
    print("len vocab size:", len(train_word_to_file.keys()))

    intersection = None
    words_index_intersect = None

    tf_idf = get_tfidf_score(files, train_word_to_file)

    if args.entities == "word2vec":
        model = gensim.models.KeyedVectors.load_word2vec_format('GoogleNews-vectors-negative300-SLIM.bin', binary=True)
        intersection, words_index_intersect  = find_intersect(model.key_to_index,  train_w_to_f_mult, model, files_num, args.entities, args.doc_info)
    elif args.entities == "fasttext":

        # for compatibility, but move everything to embeds later.
        if os.path.exists('models/wiki.en.bin'):
            ftfn = 'models/wiki.en.bin'
        else:
            ftfn = 'embeds/wiki.en.bin'

        ft = fasttext.load_model(ftfn)
        intersection, words_index_intersect = create_entities_ft(ft, train_w_to_f_mult, args.doc_info)
        print(intersection.shape)
    elif args.entities == "KG" or args.entities == "glove" :
        elmomix = [float(a) for a in args.elmomix.split(";")] if args.elmomix != "" else None
        data, word_index = read_entity_file(args.entities_file, args.id2name, train_word_to_file, args.entities, elmomix=elmomix)
        intersection, words_index_intersect = find_intersect(word_index, train_w_to_f_mult, data, files_num, args.entities, args.doc_info)

    if args.use_dims:
        intersection = PCA_dim_reduction(intersection, args.use_dims)

    #weights , tfdf = get_weights_tfdf(words_index_intersect, train_w_to_f_mult, files_num)
    weights = None
    tfdf = None

    if args.doc_info == "WGT":
        weights = get_weights_tf(words_index_intersect, train_w_to_f_mult)

    if args.doc_info == "robust":
        weights = get_rs_weights_tf(words_index_intersect, train_w_to_f_mult)

    if args.doc_info == "tfdf":
        weights , tfdf = get_weights_tfdf(words_index_intersect, train_w_to_f_mult, files_num)

    if weights is not None and args.scale == "sigmoid":
        print("scaling.. sigmoid")
        weights = 1 / (1 + np.exp(weights))


    elif weights is not None and args.scale == "log":
        print("scaling.. log")
        weights = np.log(weights)





    dev_word_to_file, dev_word_to_file_mult, dev_files = create_vocab_and_files(stopwords, args.dataset,args.preprocess, "valid", vocab)
    dev_files_num = len(dev_files)


    test_word_to_file, test_word_to_file_mult, test_files = create_vocab_and_files(stopwords, args.dataset,args.preprocess, "test", vocab)
    test_files_num = len(test_files)




    topics_npmi = []

    for topics in args.num_topics:
        npmis = []

        print("Number of Clusters:" + str(topics))
        rand = 0
        global NSEEDS
        while rand < NSEEDS:

            try:
                top_k_words, top_k = cluster(args.clustering_algo, intersection, words_index_intersect, topics, args.rerank, weights, args.topics_file, rand)
            except:
                print("Warning: failed, try diff random seed.")
                new_rand = random.randint(5,1000)
                top_k_words, top_k = cluster(args.clustering_algo, intersection, \
                        words_index_intersect, topics, args.rerank, weights, args.topics_file, new_rand)



            top_k_words = rerank(args.rerank, top_k_words, top_k, train_w_to_f_mult, train_word_to_file, tf_idf, tfdf)
            val = npmi.average_npmi_topics(top_k_words, len(top_k_words), dev_word_to_file, dev_files_num)

            if np.isnan(val):
                NSEEDS +=1
                rand += 1
                continue

            npmi_score = np.around(val, 5)
            print("NPMI:" + str(npmi_score))
            npmis.append(npmi_score)

            rand += 1

        topics_npmi.append(np.mean(npmis))
        print("NPMI Mean:" + str(np.around(topics_npmi[-1], 5)))
        print("NPMI Var:" + str(np.around(np.var(npmis), 5)))

    best_topic = args.num_topics[np.argmax(topics_npmi)]







def cluster(clustering_algo, intersection, words_index_intersect, num_topics, rerank, weights, topics_file, rand):
    if clustering_algo == "KMeans":
        labels, top_k  = KMeans_model(intersection, words_index_intersect, num_topics, rerank, rand, weights)
    elif clustering_algo == "SPKMeans":
        labels, top_k  = SphericalKMeans_model(intersection, words_index_intersect, num_topics, rerank, rand, weights)
    elif clustering_algo == "GMM":
        labels, top_k = GMM_model(intersection, words_index_intersect, num_topics, rerank, rand)
    elif clustering_algo == "KMedoids":
        labels, top_k  = KMedoids_model(intersection,  words_index_intersect,  num_topics, rand)
    elif clustering_algo == "VMFM":
        labels, top_k = VonMisesFisherMixture_Model(intersection, words_index_intersect, num_topics, rerank, rand)

    #Affinity matrix based
    elif clustering_algo == "DBSCAN":
        k=6
        labels, top_k  = DBSCAN_model(intersection,k)
    elif clustering_algo == "Agglo":
        labels, top_k  = Agglo_model(intersecticlustering_algoon, num_topics, rand)
    elif clustering_algo == "Spectral":
        labels, top_k  = SpectralClustering_Model(intersection,num_topics, rand,  weights)

    if clustering_algo == 'from_file':
        with open('bert_topics.txt', 'r') as f:
            top_k_words = f.readlines()
        top_k_words = [tw.strip().replace(',', '').split() for tw in top_k_words]

    elif clustering_algo == 'LDA':
        with open(topics_file, 'r') as f:
            top_k_words = f.readlines()
        top_k_words = [tw.strip().replace(',', '').split() for tw in top_k_words]
        for i, top_k in enumerate(top_k_words):
            top_k_words[i] = top_k_words[i][2:12]
    else:
        bins, top_k_words = sort(labels, top_k,  words_index_intersect)
    return top_k_words, np.array(top_k)


def rerank(rerank, top_k_words, top_k, train_w_to_f_mult, train_w_to_f, tf_idf, tfdf):
    if rerank=="tf":
        top_k_words =  rank_freq(top_k_words, train_w_to_f_mult)
        #top_k_words =  rank_freq(top_k_words, train_w_to_f)
    elif rerank=="tfidf":
        top_k_words = rank_td_idf(top_k_words, tf_idf)

    elif rerank=="tfdf":
        top_k_words = rank_td_idf(top_k_words, tfdf)

    elif rerank=="graph":
        #doc_matrix = npmi.calc_coo_matrix(words_index_intersect, train_word_to_file)
        top_k_words = rank_centrality(top_k_words, top_k, train_w_to_f)
    return top_k_words






def sort(labels, indices, word_index):
    bins = {}
    index = 0
    top_k_bins = []
    for label in labels:
        if label not in bins:
            bins[label] = [word_index[index]]
        else:
            bins[label].append(word_index[index])
        index += 1;
    for i in range(0, len(indices)):
        ind = indices[i]
        top_k = []
        for word_ind in ind:
            top_k.append(word_index[word_ind])
        top_k_bins.append(top_k)
    return bins, top_k_bins

def print_bins(bins, name, type):
    f = open(name + "_" + type + "_corpus_bins.txt","w+")
    for i in range(0, 20):
        f.write("Bin " + str(i) + ":\n")
        for word in bins[i]:
            f.write(word + ", ")
        f.write("\n\n")

    f.close()

def print_top_k(top_k_bins, name, type):
    f = open(name + "_" + type + "_corpus_top_k.txt","w+")
    for i in range(0, 20):
        f.write("Bin " + str(i) + ":\n")
        top_k = top_k_bins[i]
        for word in top_k:
            f.write(word + ", ")
        f.write("\n\n")
    f.close()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--entities", type=str, choices=["word2vec", "fasttext", "glove", "KG"])
    parser.add_argument( "--entities_file", type=str, help="entity file")
    parser.add_argument( "--elmomix", type=str, default="", help="elmomix coefficients, separated by ';', should sum to 1")

    parser.add_argument("--clustering_algo", type=str, required=True, choices=["KMeans", "SPKMeans", "GMM", "KMedoids","Agglo","DBSCAN","Spectral","VMFM",
        'from_file', 'LDA'])

    parser.add_argument( "--topics_file", type=str, help="topics file")

    parser.add_argument('--use_dims', type=int)
    parser.add_argument('--num_topics',  nargs='+', type=int, default=[20])
    parser.add_argument("--doc_info", type=str, choices=["SVD", "DUP", "WGT", "robust", \
    "logtfdf"])
    parser.add_argument("--rerank", type=str, choices=["tf", "tfidf", "tfdf", "graph"]) \

    parser.add_argument('--id2name', type=Path, help="id2name file")

    parser.add_argument("--dataset", type=str, default ="20NG", choices=["20NG", "children", "reuters"])

    parser.add_argument("--preprocess", type=int, default=5)
    
    parser.add_argument("--vocab", required=True,  type=str, nargs='+', default=[])
    parser.add_argument("--scale", type=str, required=False)


    args = parser.parse_args()
    return args



if __name__ == "__main__":
    main()
