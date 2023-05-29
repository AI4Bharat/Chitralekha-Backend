import json


def get_ms_time(time_str):
    h, m, s = time_str.split(":")
    ms_time = round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)
    return ms_time


def ytt_genorator(json_data, ytt_file_name, prev_line_in=0, mode="file"):
    if mode == "file":
        with open(json_data, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json_data

    # some i/p, which can be set as user i/p later
    pos_id = 7
    pos_id_prev = 11
    pen_id1 = 5
    pen_id2 = 4
    pen_id3 = 6

    # Iterating through the json
    # list
    ytt_file = open(ytt_file_name, "w")

    # write the xml format info, some of the i/p can be taken from users.
    ytt_file.write(
        '<?xml version="1.0" encoding="utf-8" ?>\n<timedtext format="3">\n<head>\n'
    )
    ytt_file.write(
        "\t<!-- Text styles -->\n"
        + '\t<pen id="1" b="1" />            <!-- Bold       -->\n'
        + '\t<pen id="2" i="1" />            <!-- Italic     -->\n'
        + '\t<pen id="3" u="1" />            <!-- Underline  -->\n'
        + "\t\n"
        + '\t<pen id="4" fc="#FFFF00" fo="254"  bo="0" bc="#080808" bo="191" ec="#FF00FF" et="4"/>\n'
        + '\t<pen id="5" fc="#FEFEFE" fo="254" bo="0" bc="#080808" bo="191"/>\n'
        + '\t<pen id="6" fc="#FEFEFE" fo="191" bo="0" bc="#080808" bo="191"/>\n'
        + "\t\n"
        + "\t<!-- Horizontal text alignment -->\n"
        + '\t<ws id="1" ju="0" />                <!-- Left   -->\n'
        + '\t<ws id="2" ju="1" />                <!-- Right  -->\n'
        + '\t<ws id="3" ju="2" />                <!-- Center -->\n'
        + "\t\n"
        + "\t<!-- Positions (ap: anchor point, ah: X coordinate (0 = left, 100 = right), av: Y coordinate (0 = top, 100 = bottom) -->\n"
        + '\t<wp id="0"  ap="0" ah="0"   av="10" />\n\t<wp id="1"  ap="0" ah="0"   av="10" />\n'
        + '\t<wp id="2"  ap="1" ah="50"  av="10" />\n\t<wp id="3"  ap="2" ah="100" av="10" />\n'
        + '\t<wp id="4"  ap="3" ah="0"   av="50" />\n'
        + '\t<wp id="5"  ap="4" ah="50"  av="50" />\n'
        + '\t<wp id="6"  ap="5" ah="100" av="50" />\n'
        + '\t<wp id="7"  ap="7" ah="50"   av="90" />\n'
        + '\t<wp id="8"  ap="7" ah="50"  av="90" />\n'
        + '\t<wp id="9"  ap="8" ah="100" av="90" />\n'
        + '\t<wp id="10" ap="1" ah="50"  av="70" />\n'
        + '\t<wp id="11" ap="7" ah="50"  av="80" />\n'
        + "</head>\n<body>"
    )

    temp_id = 0
    for j in range(1, len(data)):
        full_text = data[str(j)]["text"]

        if data[str(j)]["timestamps"] != None:
            if temp_id == 0:
                prev_line_text = ""
                temp_text = full_text
                temp_id = temp_id + 1
            else:
                prev_line_text = temp_text
                temp_text = full_text
                temp_id = temp_id + 1

            words = []
            start_timestamp_words = []
            end_timestamp_words = []

            if j < len(data) - 1:
                if data[str(j + 1)]["timestamps"] == None:
                    continue
                # next sentence start time stamp for the end of the chunck
                dict_next = data[str(j + 1)]["timestamps"][0]
                word_next = str((list(dict_next.keys())[0]))
                start_timestamp_next = get_ms_time(dict_next[word_next]["start"])
                # print(start_timestamp_next)
                # end_timestamp_words.append(get_ms_time(i[word]["end"]))

            for i in data[str(j)]["timestamps"]:
                # each words and their start and end timestamp in hh:mm:ss.ms format
                word = str((list(i.keys())[0]))
                words.append(word)
                start_timestamp_words.append(get_ms_time(i[word]["start"]))
                end_timestamp_words.append(get_ms_time(i[word]["end"]))

            for k in range(len(words)):
                highlight_str = '</s><s p="4">'
                tail_str = ' </s><s p="6">'
                end_str = "</s></p>"

                if k < (len(words) - 1):
                    if k == 0:
                        # for the first word print the first line for 10 ms
                        dur_ms = 10
                        start_str = (
                            '\n\t<p t="'
                            + str(start_timestamp_words[k])
                            + '" d="'
                            + str(dur_ms)
                            + '" wp="'
                            + str(pos_id)
                            + '" p="'
                            + str(pen_id1)
                            + '">'
                        )

                        start_str_prev = (
                            '\n\t<p t="'
                            + str(start_timestamp_words[k])
                            + '" d="'
                            + str(dur_ms)
                            + '" wp="'
                            + str(pos_id_prev)
                            + '" p="'
                            + str(pen_id1)
                            + '">'
                        )

                        # then for the rest of the time
                        line = (
                            start_str
                            + highlight_str
                            + tail_str
                            + " ".join(words)
                            + end_str
                        )
                        prev_line = (
                            start_str_prev
                            + prev_line_text
                            + highlight_str
                            + tail_str
                            + end_str
                        )
                        if prev_line_in == 1:
                            ytt_file.write(prev_line)

                        ytt_file.write(line)

                        dur_ms = (
                            start_timestamp_words[k + 1] - start_timestamp_words[k] - 10
                        )
                        start_str = (
                            '\n\t<p t="'
                            + str(start_timestamp_words[k] + 10)
                            + '" d="'
                            + str(dur_ms)
                            + '" wp="'
                            + str(pos_id)
                            + '" p="'
                            + str(pen_id1)
                            + '">'
                        )
                        # for the previous line
                        start_str_prev = (
                            '\n\t<p t="'
                            + str(start_timestamp_words[k] + 10)
                            + '" d="'
                            + str(dur_ms)
                            + '" wp="'
                            + str(pos_id_prev)
                            + '" p="'
                            + str(pen_id1)
                            + '">'
                        )

                        line = (
                            start_str
                            + highlight_str
                            + words[k]
                            + tail_str
                            + " ".join(words[1:])
                            + end_str
                        )
                        prev_line = (
                            start_str_prev
                            + prev_line_text
                            + highlight_str
                            + tail_str
                            + end_str
                        )
                        if prev_line_in == 1:
                            ytt_file.write(prev_line)

                        ytt_file.write(line)

                    else:
                        # middle words
                        dur_ms = start_timestamp_words[k + 1] - start_timestamp_words[k]
                        start_str = (
                            '\n\t<p t="'
                            + str(start_timestamp_words[k])
                            + '" d="'
                            + str(dur_ms)
                            + '" wp="'
                            + str(pos_id)
                            + '" p="'
                            + str(pen_id1)
                            + '">'
                        )

                        start_str_prev = (
                            '\n\t<p t="'
                            + str(start_timestamp_words[k])
                            + '" d="'
                            + str(dur_ms)
                            + '" wp="'
                            + str(pos_id_prev)
                            + '" p="'
                            + str(pen_id1)
                            + '">'
                        )

                        line = (
                            start_str
                            + " ".join(words[0:k])
                            + highlight_str
                            + " "
                            + words[k]
                            + tail_str
                            + " ".join(words[k + 1 :])
                            + end_str
                        )
                        prev_line = (
                            start_str_prev
                            + prev_line_text
                            + highlight_str
                            + tail_str
                            + end_str
                        )
                        if prev_line_in == 1:
                            ytt_file.write(prev_line)

                        ytt_file.write(line)
                        # line =""

                else:
                    # last words till the begining of the next chunck
                    # dur_ms =end_timestamp_words[k] -start_timestamp_words[k]
                    dur_ms = start_timestamp_next - start_timestamp_words[k]
                    start_str = (
                        '\n\t<p t="'
                        + str(start_timestamp_words[k])
                        + '" d="'
                        + str(dur_ms)
                        + '" wp="'
                        + str(pos_id)
                        + '" p="'
                        + str(pen_id1)
                        + '">'
                    )

                    start_str_prev = (
                        '\n\t<p t="'
                        + str(start_timestamp_words[k])
                        + '" d="'
                        + str(dur_ms)
                        + '" wp="'
                        + str(pos_id_prev)
                        + '" p="'
                        + str(pen_id1)
                        + '">'
                    )

                    line = (
                        start_str
                        + " ".join(words[0:k])
                        + highlight_str
                        + " "
                        + words[k]
                        + tail_str
                        + " ".join(words[k + 1 :])
                        + end_str
                    )
                    prev_line = (
                        start_str_prev
                        + prev_line_text
                        + highlight_str
                        + tail_str
                        + end_str
                    )
                    if prev_line_in == 1:
                        ytt_file.write(prev_line)

                    ytt_file.write(line + "\n")

    ytt_file.write("</body>\n</timedtext>")
    # Closing file
    ytt_file.close()


if __name__ == "__main__":
    json_file_name = "alignment.json"
    ytt_file_name = "myfileYT_test.ytt"
    prev_line_in = 0  # 1 for 2 line caption per frame, 0 for single line.
    ytt_genorator(json_file_name, ytt_file_name)
