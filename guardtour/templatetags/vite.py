import json
import os
from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def vite_asset(name, asset_type='file'):
    """Resolve a Vite-built asset path from the build manifest.

    Returns the full URL path (including STATIC_URL prefix).

    Usage:
      {% vite_asset 'src/main.js' %}        -> '/static/dist/assets/main-abc123.js'
      {% vite_asset 'src/main.js' 'css' %}  -> '/static/dist/assets/main-abc123.css'
    """
    manifest_path = os.path.join(settings.BASE_DIR, 'static', 'dist', '.vite', 'manifest.json')
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        entry = manifest.get(name)
        if entry:
            if asset_type == 'css' and entry.get('css'):
                return settings.STATIC_URL + 'dist/' + entry['css'][0]
            return settings.STATIC_URL + 'dist/' + entry['file']
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass
    return settings.STATIC_URL + f'dist/assets/{name.split("/")[-1]}'
