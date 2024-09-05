


def extract_number(input_string):
    matches = re.findall(r'\d+', input_string)

    if matches:
        if len(matches) == 1:
            return int(matches[0])
        else:
            return tuple(map(int, matches))
    else:
        return None

