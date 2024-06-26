def generate_ttml(payload):
    lines = []
    lines.append(
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        + "<tt xmlns='http://www.w3.org/ns/ttml' xmlns:ttp='http://www.w3.org/ns/ttml#parameter' xmlns:tts='http://www.w3.org/ns/ttml#styling' xmlns:ttm='http://www.w3.org/ns/ttml#metadata' xmlns:xml='http://www.w3.org/XML/1998/namespace' ttp:timeBase='media' ttp:frameRate='24' xml:lang='en'>\n"
        + "\t<head>\n"
        + "\t\t<metadata>\n"
        + "\t\t\t<ttm:title>Sample TTML</ttm:title>\n"
        + "\t\t</metadata>\n"
        + "\t\t<styling>\n"
        + "\t\t\t<style xml:id='s1' tts:textAlign='center' tts:fontFamily='Arial' tts:fontSize='100%'/>\n"
        + "\t\t</styling>\n"
        + "\t\t<layout>\n"
        + "\t\t\t<region xml:id='bottom' tts:displayAlign='after' tts:extent='80% 40%' tts:origin='10% 50%'/>\n"
        + "\t\t\t<region xml:id='top' tts:displayAlign='before' tts:extent='80% 40%' tts:origin='10% 10%'/>\n"
        + "\t\t</layout>\n"
        + "\t</head>\n"
        + "\t<body>\n"
        + "\t\t<div>\n"
    )
    return lines
