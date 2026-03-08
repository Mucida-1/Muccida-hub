

def get_nested_value(d, path):
    if not path or not d: return None
    keys = path.split('.')
    val = d
    for key in keys:
        if isinstance(val, dict):
            val = val.get(key)
        else:
            return None
    return val