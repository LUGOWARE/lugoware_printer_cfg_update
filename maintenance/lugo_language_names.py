"""Native language labels; locale codes remain unchanged in callbacks."""
NAMES = {
 'ar':'العربية', 'bg':'Български', 'cs':'Čeština', 'da':'Dansk',
 'de':'Deutsch', 'de_formal':'Deutsch (formell)', 'en':'English', 'es':'Español',
 'et':'Eesti', 'fa':'فارسی', 'fr':'Français', 'he':'עברית', 'hr':'Hrvatski',
 'hu':'Magyar', 'it':'Italiano', 'jp':'日本語', 'ko':'한국어', 'lt':'Lietuvių',
 'nl':'Nederlands', 'pl':'Polski', 'pt':'Português', 'pt_BR':'Português (Brasil)',
 'rs':'Српски', 'ru':'Русский', 'sk':'Slovenčina', 'sl':'Slovenščina',
 'sv':'Svenska', 'tr':'Türkçe', 'uk':'Українська', 'vi':'Tiếng Việt',
 'zh_CN':'中文（简体）', 'zh_TW':'中文（繁體）',
}

def language_name(code):
    if code == 'system_lang':
        import builtins
        return getattr(builtins, '_', lambda x:x)('System language')
    return NAMES.get(code, code)
