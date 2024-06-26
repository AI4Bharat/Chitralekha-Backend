from sentence_transformers import SentenceTransformer
import sys
from sentence_transformers import SentenceTransformer
import numpy as np
from scipy.spatial import distance

aligned_phrases = {}
model_name = "sentence-transformers/LaBSE"
model = SentenceTransformer(model_name)
sentences = ["ढाँचा", "work"]


def split_tgt(length_src_phrase, tgt):
    tgt_token_list = list()
    # tokenised_tgt_ =  indic_tok.trivial_tokenize(tgt)
    tokenised_tgt = tgt.split()
    tgt_token_list = [
        tokenised_tgt[i : i + length_src_phrase]
        for i in range(len(tokenised_tgt))
        if (i + length_src_phrase) <= len(tokenised_tgt)
    ]
    tgt_token_list_plus = [
        tokenised_tgt[i : i + length_src_phrase + 1]
        for i in range(len(tokenised_tgt))
        if (i + length_src_phrase + 1) <= len(tokenised_tgt)
    ]
    tgt_token_list_minus = [
        tokenised_tgt[i : i + length_src_phrase - 1]
        for i in range(len(tokenised_tgt))
        if (i + length_src_phrase - 1) <= len(tokenised_tgt) and length_src_phrase != 1
    ]
    tgt_token_list = tgt_token_list + tgt_token_list_plus + tgt_token_list_minus
    tgt_token_list = [" ".join(j) for j in tgt_token_list]
    if len(tgt_token_list) == 0:
        tgt_token_list = [tgt]
    return tgt_token_list


def generate_embeddings(input_1, input_2):
    """
    Generate LABSE embeddings
    Note: Inputs are array of strings
    """
    embeddings_input_1 = model.encode(input_1, show_progress_bar=True)
    embeddings_input_2 = model.encode(input_2, show_progress_bar=True)

    return embeddings_input_1, embeddings_input_2


def get_target_sentence(target_embeddings, source_embedding, length_src_phrase):
    """
    Calculate cosine similarity using scipy distance method
    """
    distances = distance.cdist(source_embedding, target_embeddings, "cosine")[0]
    min_index = np.argmin(distances)
    min_distance = 1 - distances[min_index]

    if min_distance >= 0.5:
        return min_index, min_distance, "MATCH"
    else:
        return min_index, min_distance, "NOMATCH"


tgt_token_list = split_tgt(8, sentences[1])
# Our sentences we like to encode


# Sentences are encoded by calling model.encode()
embeddings_src_phrase, embeddings_tgt_tokens = generate_embeddings(
    [sentences[0]], tgt_token_list
)
alignments = get_target_sentence(embeddings_tgt_tokens, embeddings_src_phrase, 8)

if alignments is not None and alignments[2] == "MATCH":
    aligned_phrases[sentences[0]] = tgt_token_list[alignments[0]]
elif alignments is not None and alignments[2] == "NOMATCH":
    print("no exact match found")
else:
    print("here")

print(aligned_phrases)
