import hashlib
import json
import time
from datetime import datetime
import uuid
import requests
from .tmxrepo import TMXRepository
import logging
from glossary.labse_ailigner import *
import re
from users.models import User
from glossary.models import Glossary


repo = TMXRepository()


class TMXService:
    def __init__(self):
        pass

    # Pushes translations to the tmx.
    def push_to_tmx_store(self, tmx_input):
        if not tmx_input["sentences"]:
            return {"message": "Sentences list cannot be empty", "status": "FAILED"}
        for sentence in tmx_input["sentences"]:
            tmx_records = []
            sentence_types, i = (
                self.fetch_diff_flavors_of_sentence(sentence["src"]),
                0,
            )
            current_time = datetime.now().strftime("%s")
            for sent in sentence_types:
                tmx_record_pair = {
                    "src": sent,
                    "locale": sentence["locale"],
                    "nmt_tgt": [],
                    "user_tgt": sentence["tgt"],
                }
                if "userID" in tmx_input.keys():
                    tmx_record_pair["userID"] = tmx_input["userID"]
                """
                    if "orgID" in tmx_input.keys():
                        tmx_record_pair["orgID"] = tmx_input["orgID"]
                    """
                if i == 0:
                    tmx_record_pair["original"] = True
                tmx_record_pair["timestamp"] = current_time
                tmx_records.append(tmx_record_pair)
                i += 1
            reverse_locale_array = str(sentence["locale"]).split("|")
            reverse_locale = (
                str(reverse_locale_array[1]) + "|" + str(reverse_locale_array[0])
            )
            tmx_record_reverse_pair = {
                "src": sentence["tgt"],
                "locale": reverse_locale,
                "nmt_tgt": [],
                "user_tgt": sentence["src"],
            }
            if "userID" in tmx_input.keys():
                tmx_record_reverse_pair["userID"] = tmx_input["userID"]
            """
                if "orgID" in tmx_input.keys():
                    tmx_record_reverse_pair["orgID"] = tmx_input["orgID"]
                """
            tmx_record_reverse_pair["timestamp"] = current_time
            tmx_records.append(tmx_record_reverse_pair)
            for tmx_record in tmx_records:
                hash_dict = self.get_hash_key(tmx_record)
                for hash_key in hash_dict.keys():
                    tmx_record["hash"] = hash_dict[hash_key]
                    repo.upsert(tmx_record["hash"], tmx_record)
        self.push_tmx_metadata(tmx_input, None)
        logging.info("Translations pushed to TMX!")
        return {"message": "Glossary entry created", "status": "SUCCESS"}

    # Method to push tmx related metadata
    def push_tmx_metadata(self, tmx_record, file_path):
        locale, length = tmx_record["sentences"][0]["locale"], len(
            tmx_record["sentences"]
        )
        db_record = tmx_record
        db_record["timeStamp"] = eval(str(time.time()).replace(".", "")[0:13])
        repo.tmx_create(db_record)
        db_record_reverse = tmx_record
        reverse_locale_array = str(locale).split("|")
        reverse_locale = (
            str(reverse_locale_array[1]) + "|" + str(reverse_locale_array[0])
        )
        db_record_reverse["timeStamp"] = eval(str(time.time()).replace(".", "")[0:13])
        repo.tmx_create(db_record_reverse)

    # Method to delete records from TMX store.
    def delete_from_tmx_store(self, tmx_input):
        logging.info("Deleting to Glossary......")
        hashes = []
        if "sentences" not in tmx_input.keys():
            try:
                if "orgID" in tmx_input.keys():
                    search_req = {
                        "orgID": tmx_input["orgID"],
                        "userID": "userID",
                        "allUserKeys": True,
                    }
                    tmx_to_be_deleted = self.get_tmx_data(search_req)
                else:
                    search_req = {
                        "userID": tmx_input["userID"],
                        "orgID": "orgID",
                        "allUserKeys": True,
                    }
                    tmx_to_be_deleted = self.get_tmx_data(search_req)

                if tmx_to_be_deleted:
                    for tmx_del in tmx_to_be_deleted:
                        hashes.append(tmx_del["hash"])
                    repo.delete(hashes)
                    logging.info("Glossary deleted!")
                    return {"message": "Glossary DELETED!", "status": "SUCCESS"}
                else:
                    logging.info("No Glossary Available!")
                    return {"message": "No Glossary Available!", "status": "SUCCESS"}
            except Exception as e:
                logging.info(
                    "Exception while deleting Glossary by orgID/userID: " + str(e)
                )
                return {
                    "message": "deletion of Glossary by orgID/userID failed",
                    "status": "FAILED",
                }
        else:
            if not tmx_input["sentences"]:
                logging.info("No sentences sent for deletion!")
                return {
                    "message": "No sentences sent for deletion!",
                    "status": "SUCCESS",
                }
            try:
                tmx_records = []
                for sentence in tmx_input["sentences"]:
                    sentence_list = [sentence]
                    rev_locale = f'{str(sentence["locale"]).split("|")[1]}|{str(sentence["locale"]).split("|")[0]}'
                    rev_pair = {
                        "src": sentence["tgt"],
                        "tgt": sentence["src"],
                        "locale": rev_locale,
                    }
                    sentence_list.append(rev_pair)
                    for tmx in sentence_list:
                        sentence_types = self.fetch_diff_flavors_of_sentence(tmx["src"])
                        for sent in sentence_types:
                            tmx_record_pair = {
                                "src": sent,
                                "locale": tmx["locale"],
                                "nmt_tgt": [],
                                "user_tgt": tmx["tgt"],
                            }
                            if "userID" in tmx_input.keys():
                                tmx_record_pair["userID"] = tmx_input["userID"]
                            tmx_records.append(tmx_record_pair)

                for tmx_record in tmx_records:
                    hash_dict = self.get_hash_key(tmx_record)
                    hashes.extend(hash_dict.values())
                    user_id = User.objects.get(pk=int(tmx_record["userID"]))
                    glossary_obj = Glossary.objects.filter(
                        source_text=tmx_record["src"],
                        target_text=tmx_record["user_tgt"],
                        source_language=tmx_record["locale"].split("|")[0],
                        target_language=tmx_record["locale"].split("|")[1],
                        user_id=user_id,
                    )
                    if glossary_obj is not None:
                        glossary_obj.delete()
                repo.delete(hashes)
                logging.info("Glossary deleted!")
                return {"message": "Glossary DELETED!", "status": "SUCCESS"}
            except Exception as e:
                logging.info("Exception while deleting Glossary one by one: " + str(e))
                return {
                    "message": "deletion of Glossary one by one failed",
                    "status": "FAILED",
                }

    # Method to fetch tmx phrases for a given src
    def get_tmx_phrases(self, user_id, org_id, locale, sentence, tmx_level):
        tmx_record = {"locale": locale, "src": sentence}
        if user_id:
            tmx_record["userID"] = user_id
        tmx_phrases, res_dict = self.tmx_phrase_search(tmx_record, tmx_level)
        return tmx_phrases, res_dict

    # Generates a 3 flavors for a sentence - title case, lowercase and uppercase.
    def fetch_diff_flavors_of_sentence(self, sentence):
        result = []
        org_sentence = str(sentence)
        result.append(org_sentence)
        title = org_sentence.title()
        if org_sentence != title:
            result.append(title)
        small = org_sentence.lower()
        if org_sentence != small:
            result.append(small)
        caps = org_sentence.upper()
        if org_sentence != caps:
            result.append(caps)
        return result

    # Searches for all tmx phrases of a fixed length within a given sentence
    # Uses a custom implementation of the sliding window search algorithm - we call it hopping window.
    def tmx_phrase_search(self, tmx_record, tmx_level):
        tmx_word_length = 4
        sentence, tmx_phrases = tmx_record["src"], []
        hopping_pivot, sliding_pivot, i = 0, len(sentence), 1
        computed, r_count, c_count = (
            0,
            0,
            0,
        )
        while hopping_pivot < len(sentence):
            phrase = sentence[hopping_pivot:sliding_pivot]
            phrase_size = phrase.split(" ")
            if len(phrase_size) <= tmx_word_length:
                suffix_phrase_list, found = [phrase], False
                if phrase.endswith(".") or phrase.endswith(","):
                    short = phrase.rstrip(".,")
                    suffix_phrase_list.append(short)
                for phrases in suffix_phrase_list:
                    tmx_record["src"] = phrases
                    tmx_result, fetch = self.get_tmx_with_fallback(
                        tmx_record, tmx_level
                    )
                    computed += 1
                    if tmx_result:
                        # logging.info(f"Test68 phrase {tmx_record}, result {tmx_result}")
                        tmx_phrases.append(tmx_result[0])
                        phrase_list = phrase.split(" ")
                        hopping_pivot += 1 + len(" ".join(phrase_list))
                        sliding_pivot = len(sentence)
                        i = 1
                        if fetch is True:
                            r_count += 1
                        else:
                            c_count += 1
                        found = True
                        break
                if found:
                    continue
            sent_list = sentence.split(" ")
            phrase_list = phrase.split(" ")
            reduced_phrase = " ".join(sent_list[0 : len(sent_list) - i])
            sliding_pivot = len(reduced_phrase)
            i += 1
            if hopping_pivot == sliding_pivot or (hopping_pivot - 1) == sliding_pivot:
                hopping_pivot += 1 + len(" ".join(phrase_list))
                sliding_pivot = len(sentence)
                i = 1
        # except Exception as e:
        #    logging.info("Exception in Hopping Window Search: {}".format(e))
        res_dict = {"computed": computed, "redis": r_count, "cache": c_count}
        return tmx_phrases, res_dict

    # Fetches TMX phrases for a sentence from hierarchical cache
    def get_tmx_with_fallback(self, tmx_record, tmx_level):
        hash_dict = self.get_hash_key_search(tmx_record, tmx_level)
        # logging.info(f"Test68 hash_dict {hash_dict}")
        if "USER" in hash_dict.keys():
            tmx_result = repo.search([hash_dict["USER"]])
            if tmx_result:
                # logging.info(f"Test68 USER tmx_result {tmx_result}")
                # tmx_file_cache[hash_dict["USER"]] = tmx_result
                return tmx_result, True
            else:
                return None, False
        if "ORG" in hash_dict.keys():
            if hash_dict["ORG"] not in tmx_file_cache.keys():
                tmx_result = repo.search([hash_dict["ORG"]])
                if tmx_result:
                    # logging.info(f"Test68 ORG tmx_result {tmx_result}")
                    tmx_file_cache[hash_dict["ORG"]] = tmx_result
                    return tmx_result, True
            else:
                return tmx_file_cache[hash_dict["ORG"]], False
        if "GLOBAL" in hash_dict.keys():
            if hash_dict["GLOBAL"] not in tmx_file_cache.keys():
                tmx_result = repo.search([hash_dict["GLOBAL"]])
                if tmx_result:
                    tmx_file_cache[hash_dict["GLOBAL"]] = tmx_result
                    return tmx_result, True
            else:
                return tmx_file_cache[hash_dict["GLOBAL"]], False
        return None, False

    # Replaces TMX phrases in NMT tgt using TMX NMT phrases and LaBSE alignments
    def replace_nmt_tgt_with_user_tgt(self, tmx_phrases, src, tgt):
        tmx_without_nmt_phrases, tmx_tgt, tmx_replacement = [], None, []

        try:
            tmx_replace_dict = {}
            for tmx_phrase in tmx_phrases:
                if tmx_phrase["nmt_tgt"]:
                    found = False
                    for nmt_tgt_phrase in tmx_phrase["nmt_tgt"]:
                        if nmt_tgt_phrase in tgt:
                            tmx_replacement.append(
                                {
                                    "src_phrase": tmx_phrase["src"],
                                    "tmx_tgt": tmx_phrase["user_tgt"],
                                    "tgt": str(nmt_tgt_phrase),
                                    "type": "NMT",
                                }
                            )
                            tmx_replace_dict[nmt_tgt_phrase] = tmx_phrase["user_tgt"]
                            found = True
                            break
                    if not found:
                        tmx_without_nmt_phrases.append(tmx_phrase)
                else:
                    tmx_without_nmt_phrases.append(tmx_phrase)
            if tmx_replace_dict:
                tgt = self.multiple_replace(tgt, tmx_replace_dict)
            tmx_tgt = tgt
            if tmx_without_nmt_phrases:
                logging.info(
                    "Phrases to LaBSE: {} | Total: {}".format(
                        len(tmx_without_nmt_phrases), len(tmx_phrases)
                    )
                )
                tmx_tgt, tmx_replacement = self.replace_with_labse_alignments(
                    tmx_without_nmt_phrases, tgt, tmx_replacement
                )
            if tmx_tgt:
                return tmx_tgt, tmx_replacement
            else:
                return tgt, tmx_replacement
        except Exception as e:
            logging.info(
                "Exception while replacing nmt_tgt with user_tgt: {}".format(e)
            )
            return tgt, tmx_replacement

    # Replaces phrases in tgt with user tgts using labse alignments and updates nmt_tgt in TMX
    def replace_with_labse_alignments(self, tmx_phrases, tgt, tmx_replacement):
        labse_aligner_resource = LabseAlignerResource()
        tmx_phrase_dict, tmx_replace_dict = {}, {}
        for tmx_phrase in tmx_phrases:
            tmx_phrase_dict[tmx_phrase["src"]] = tmx_phrase
        nmt_req = {"src_phrases": list(tmx_phrase_dict.keys()), "tgt": tgt}
        nmt_req = [nmt_req]
        api_headers = {"Content-Type": "application/json"}
        nmt_response = labse_aligner_resource.post(nmt_req)
        if type(nmt_response) == list:
            nmt_aligned_phrases = nmt_response[0]["aligned_phrases"]
            if nmt_aligned_phrases:
                for aligned_phrase in nmt_aligned_phrases.keys():
                    phrase = tmx_phrase_dict[aligned_phrase]
                    tmx_replacement.append(
                        {
                            "src_phrase": phrase["src"],
                            "tmx_tgt": phrase["user_tgt"],
                            "tgt": str(nmt_aligned_phrases[aligned_phrase]),
                            "type": "LaBSE",
                        }
                    )
                    tmx_replace_dict[nmt_aligned_phrases[aligned_phrase]] = phrase[
                        "user_tgt"
                    ]
                    modified_nmt_tgt = phrase["nmt_tgt"]
                    modified_nmt_tgt.append(nmt_aligned_phrases[aligned_phrase])
                    phrase["nmt_tgt"] = modified_nmt_tgt
                    repo.upsert(phrase["hash"], phrase)
                    if tmx_replace_dict:
                        tgt = self.multiple_replace(tgt, tmx_replace_dict)
                    else:
                        logging.info("No LaBSE alignments found!")
                        logging.info("LaBSE - " + str(nmt_req))
                    return tgt, tmx_replacement
            else:
                return tgt, tmx_replacement
        else:
            return tgt, tmx_replacement

    # Method to simultaneously replace multiple strings in a sentence
    def multiple_replace(self, sentence, replacement_dict):
        pattern = re.compile(
            "|".join(
                [re.escape(k) for k in sorted(replacement_dict, key=len, reverse=True)]
            ),
            flags=re.DOTALL,
        )
        return pattern.sub(lambda x: replacement_dict[x.group(0)], sentence)

    # Replaces phrases in tgt with user tgts using labse alignments and updates nmt_tgt in TMX
    def replace_with_attention_api(self, tmx_phrases, src, tgt, tmx_replacement, ctx):
        tmx_phrase_dict, tmx_replace_dict = {}, {}
        for tmx_phrase in tmx_phrases:
            tmx_phrase_dict[tmx_phrase["src"]] = tmx_phrase
        nmt_req = {"src": src, "src_phrases": list(tmx_phrase_dict.keys()), "tgt": tgt}
        nmt_req = [nmt_req]
        api_headers = {"Content-Type": "application/json"}
        nmt_response = requests.post(
            url=nmt_attention_align_url, json=nmt_req, headers=api_headers
        )
        # logging.info(f"NMT Response with Attention API {nmt_response.json}",None)
        if nmt_response:
            if nmt_response.text:
                nmt_response = json.loads(nmt_response.text)
            if "status" in nmt_response.keys():
                if nmt_response["status"]["statusCode"] != 200:
                    logging.info(
                        "Attention API Error: {}".format(
                            nmt_response["status"]["message"]
                        )
                    )
                    return tgt, tmx_replacement
                else:
                    nmt_aligned_phrases = nmt_response["response_body"][0][
                        "aligned_phrases"
                    ]
                    if nmt_aligned_phrases:
                        for aligned_phrase in nmt_aligned_phrases.keys():
                            phrase = tmx_phrase_dict[aligned_phrase]
                            tmx_replacement.append(
                                {
                                    "src_phrase": phrase["src"],
                                    "tmx_tgt": phrase["user_tgt"],
                                    "tgt": str(nmt_aligned_phrases[aligned_phrase]),
                                    "type": "Attention API",
                                }
                            )
                            tmx_replace_dict[
                                nmt_aligned_phrases[aligned_phrase]
                            ] = phrase["user_tgt"]
                            modified_nmt_tgt = phrase["nmt_tgt"]
                            modified_nmt_tgt.append(nmt_aligned_phrases[aligned_phrase])
                            phrase["nmt_tgt"] = modified_nmt_tgt
                            repo.upsert(phrase["hash"], phrase)
                        if tmx_replace_dict:
                            tgt = self.multiple_replace(tgt, tmx_replace_dict)
                    else:
                        logging.info("No Attention API alignments found!")
                        logging.info("Attention API - " + str(nmt_req))
                    return tgt, tmx_replacement
            else:
                return tgt, tmx_replacement
        else:
            return tgt, tmx_replacement

    def sort_redis_records_timestamp(self, record):
        if "timestamp" in record.keys():
            return eval(record["timestamp"])
        else:
            return 0

    # Method to fetch all keys from the redis db
    def get_tmx_data(self, req):
        logging.info(f"Searching TMX for: {req}")
        if "keys" in req.keys():
            if req["keys"]:
                return repo.get_all_records(req["keys"])
        elif "getAll" in req.keys():
            if req["getAll"]:
                return repo.get_all_records([])
        a = 1
        if a == 1:
            redis_records = repo.get_all_records([])
            logging.info(f"No of tmx entries fetched: {len(redis_records)}")
            user_id, org_id = req["userID"], 1
            if redis_records:
                filtered = filter(
                    lambda record: self.filter_user_records(record, user_id, org_id),
                    redis_records,
                )
                if filtered:
                    redis_records = list(filtered)
                    logging.info(
                        f"No of tmx entries filtered by user & org: {len(redis_records)}"
                    )
                else:
                    logging.info(f"No TMX entries found for this user!")
                    redis_records = []
                if redis_records:
                    if "allUserKeys" in req.keys():
                        if req["allUserKeys"]:
                            return redis_records
                    filtered = filter(
                        lambda record: self.filter_original_keys(record), redis_records
                    )

                    if filtered:
                        redis_records = list(filtered)
                    else:
                        redis_records = []
            logging.info(f"Count of final TMX to be returned: {len(redis_records)}")
            sorted_redis_records = sorted(
                redis_records, key=self.sort_redis_records_timestamp, reverse=True
            )
            return sorted_redis_records

    def filter_user_records(self, record, user_id, org_id):
        if "userID" in record.keys():
            return record["userID"] == user_id
        elif "orgID" in record.keys():
            return record["orgID"] == org_id
        else:
            return False

    def filter_original_keys(self, record):
        try:
            if "original" in record.keys():
                return record["original"]
            else:
                return False
        except Exception as e:
            logging.info(f"RECORD: {record}")
            logging.info(f"Exception while filtering on original: {e}")
            return False

    # Creates a md5 hash values using userID, orgID, context, locale and src for inserting records.
    def get_hash_key(self, tmx_record):
        hash_dict = {}
        if "orgID" in tmx_record.keys():
            org_hash = (
                tmx_record["orgID"]
                + "__"
                + tmx_record["locale"]
                + "__"
                + tmx_record["src"]
            )
            hash_dict["ORG"] = hashlib.sha256(org_hash.encode("utf-16")).hexdigest()
        if "userID" in tmx_record.keys():
            user_hash = (
                tmx_record["userID"]
                + "__"
                + tmx_record["locale"]
                + "__"
                + tmx_record["src"]
            )
            hash_dict["USER"] = hashlib.sha256(user_hash.encode("utf-16")).hexdigest()
        return hash_dict

    # Creates a md5 hash values using userID, orgID, context, locale and src for searching records.
    def get_hash_key_search(self, tmx_record, tmx_level):
        hash_dict = {}
        tmx_global_enabled = False
        tmx_user_enabled = True
        tmx_org_enabled = False
        if tmx_global_enabled:
            global_hash = +tmx_record["locale"] + "__" + tmx_record["src"]
            hash_dict["GLOBAL"] = hashlib.sha256(
                global_hash.encode("utf-16")
            ).hexdigest()
        if tmx_level is None:
            return hash_dict
        if tmx_level == "BOTH":
            if tmx_org_enabled:
                org_hash = (
                    tmx_record["orgID"]
                    + "__"
                    + tmx_record["locale"]
                    + "__"
                    + tmx_record["src"]
                )
                hash_dict["ORG"] = hashlib.sha256(org_hash.encode("utf-16")).hexdigest()
            if tmx_user_enabled:
                user_hash = (
                    tmx_record["userID"]
                    + "__"
                    + tmx_record["locale"]
                    + "__"
                    + tmx_record["src"]
                )
                hash_dict["USER"] = hashlib.sha256(
                    user_hash.encode("utf-16")
                ).hexdigest()
        elif tmx_level == "USER" and tmx_user_enabled:
            user_hash = (
                tmx_record["userID"]
                + "__"
                + tmx_record["locale"]
                + "__"
                + tmx_record["src"]
            )
            hash_dict["USER"] = hashlib.sha256(user_hash.encode("utf-16")).hexdigest()
        elif tmx_level == "ORG" and tmx_org_enabled:
            org_hash = (
                tmx_record["orgID"]
                + "__"
                + tmx_record["locale"]
                + "__"
                + tmx_record["src"]
            )
            hash_dict["ORG"] = hashlib.sha256(org_hash.encode("utf-16")).hexdigest()
        return hash_dict

    # Method creates entry to the suggestion box, admin pulls these suggestions once in a while and selects which
    # must go to ORG level TMX.
    def suggestion_box_create(self, object_in):
        try:
            suggested_translations = []
            for translation in object_in["translations"]:
                translation["id"], translation["orgID"] = (
                    str(uuid.uuid4()),
                    object_in["orgID"],
                )
                translation["uploadedBy"] = object_in["metadata"]["userID"]
                translation["createdOn"] = eval(str(time.time()).replace(".", "")[0:13])
                translation["updatedOn"] = eval(str(time.time()).replace(".", "")[0:13])
                translation["status"] = "Pending"
                suggested_translations.append(translation)
            if suggested_translations:
                inserts = repo.suggestion_box_create(suggested_translations)
                logging.info(f"Insert IDS: {inserts}", None)
                return {
                    "message": "Suggestions created successfully",
                    "status": "SUCCESS",
                }
            return {"message": "No Suggestions created!", "status": "SUCCESS"}
        except Exception as e:
            return post_error(
                "SUGGESTION_BOX_CREATION_FAILED",
                "Suggestions creation failed due to exception: {}".format(str(e)),
                None,
            )

    # Method updates entry to the suggestion box
    def suggestion_box_update(self, object_in):
        try:
            find_condition = {"id": {"$in": object_in["ids"]}}
            if object_in["status"] == "Modified":
                set_clause = {
                    "status": object_in["status"],
                    "src": object_in["src"],
                    "tgt": object_in["tgt"],
                    "updatedOn": eval(str(time.time()).replace(".", "")[0:13]),
                }
            else:
                set_clause = {
                    "status": object_in["status"],
                    "updatedOn": eval(str(time.time()).replace(".", "")[0:13]),
                }
            repo.suggestion_box_update(find_condition, {"$set": set_clause})
            return {"message": "Suggestions Updated !", "status": "SUCCESS"}
        except Exception as e:
            return post_error(
                "SUGGESTION_BOX_UPDATE_FAILED",
                "Suggestions update failed due to exception: {}".format(str(e)),
                None,
            )

    # Method to delete suggestions from the db
    def suggestion_box_delete(self, delete_req):
        query = {}
        if "deleteAll" in delete_req.keys():
            if delete_req["deleteAll"] is True:
                repo.suggestion_box_delete(query)
                return {
                    "message": "Suggestion Box DB cleared successfully",
                    "status": "SUCCESS",
                }
        if "ids" in delete_req.keys():
            if delete_req["ids"]:
                query = {"id": {"$in": delete_req["ids"]}}
        if "userIDs" in delete_req.keys():
            if delete_req["userIDs"]:
                query["uploadedBy"] = {"$in": delete_req["userIDs"]}
        if "orgIDs" in delete_req.keys():
            if delete_req["orgIDs"]:
                query["orgID"] = {"$in": delete_req["orgIDs"]}
        if "startDate" in delete_req.keys():
            query["createdOn"] = {"$gte": delete_req["startDate"]}
        if "endDate" in delete_req.keys():
            query["createdOn"] = {"$lte": delete_req["endDate"]}
        if query:
            query["status"] = "Pending"
            logging.info(f"Delete Query: {query}")
            del_count = repo.suggestion_box_delete(query)
            if del_count > 0:
                return {
                    "message": "Suggestions pending for approval deleted successfully",
                    "status": "SUCCESS",
                }
        return {"message": "No Suggestions deleted", "status": "SUCCESS"}

    # Method to search suggestions from the suggestions db.
    def suggestion_box_get(self, search_req):
        query, exclude = {}, {"_id": False}
        if "fetchAll" in search_req.keys():
            if search_req["fetchAll"] is True:
                return repo.suggestion_box_search(query, exclude)
        if "ids" in search_req.keys():
            if search_req["ids"]:
                query = {"id": {"$in": search_req["ids"]}}
        if "src" in search_req.keys():
            if search_req["src"]:
                query["src"] = search_req["src"]
        if "tgt" in search_req.keys():
            if search_req["tgt"]:
                query["tgt"] = search_req["tgt"]
        if "locale" in search_req.keys():
            if search_req["locale"]:
                query["locale"] = search_req["locale"]
        if "orgIDs" in search_req.keys():
            if search_req["orgIDs"]:
                query["orgID"] = {"$in": search_req["orgIDs"]}
        if "userIDs" in search_req.keys():
            if search_req["userIDs"]:
                query["uploadedBy"] = {"$in": search_req["userIDs"]}
        if "statuses" in search_req.keys():
            if search_req["statuses"]:
                query["status"] = {"$in": search_req["statuses"]}
        if "startDate" in search_req.keys():
            query["createdOn"] = {"$gte": search_req["startDate"]}
        if "endDate" in search_req.keys():
            query["createdOn"] = {"$lte": search_req["endDate"]}
        if query:
            logging.info(f"Search Query: {query}")
            return repo.suggestion_box_search(query, exclude)
        else:
            return []
