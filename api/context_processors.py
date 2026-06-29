def base_template_context(request):
    """Injects base_template variable for SPA navigation.
    
    Returns 'bare_base.html' for htmx requests (partial content),
    'base_app.html' for full page loads.
    """
    is_htmx = bool(request.headers.get('HX-Request')) if request else False
    return {
        'base_template': 'bare_base.html' if is_htmx else 'base_template.html',
    }
