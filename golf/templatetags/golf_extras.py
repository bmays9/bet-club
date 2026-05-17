# golf/templatetags/golf_extras.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Look up a dict value by key in a template. Usage: {{ mydict|get_item:key }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter
def picked_by_name(picked_by_dict, golfer_id):
    """Return username of who picked a golfer. Usage: {{ picked_by|picked_by_name:golfer.id }}"""
    if isinstance(picked_by_dict, dict):
        return picked_by_dict.get(golfer_id, "")
    return ""
