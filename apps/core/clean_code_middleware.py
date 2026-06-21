"""
==========================================================================
 CLEAN CODE MIDDLEWARE - Comment Stripper (v4 - FINAL)
==========================================================================
 Menghapus SEMUA komentar developer dari response HTML sebelum dikirim
 ke browser: HTML comments, CSS comments, JS comments, dan Django
 template comments yang lolos dari template engine.
==========================================================================
"""
import re
import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# Pre-compile regex patterns
_RE_HTML_COMMENT = re.compile(r'<!--(?!\s*\[if)(?!\s*\[endif).*?-->', re.DOTALL)
_RE_CSS_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
_RE_DJANGO_COMMENT = re.compile(r'\{#.*?#\}', re.DOTALL)


def _is_regex_context(result_so_far):
    """Check if / at current position starts a regex literal (not division)."""
    stripped = ''.join(result_so_far).rstrip()
    if not stripped:
        return True
    last_char = stripped[-1]
    # After these chars, / is regex
    if last_char in '=(:,;![&|?{+\n~^<>*%':
        return True
    # After return/typeof/instanceof/in keywords
    for kw in ('return', 'typeof', 'instanceof', 'in', 'delete', 'void', 'throw',
               'new', 'case', 'yield', 'await'):
        if stripped.endswith(kw) and (len(stripped) == len(kw) or not stripped[-len(kw) - 1].isalnum()):
            return True
    return False


def _consume_regex(js_text, start):
    """Consume a regex literal /pattern/flags starting at position start."""
    i = start + 1  # skip opening /
    length = len(js_text)
    chars = ['/']
    in_class = False
    while i < length:
        c = js_text[i]
        chars.append(c)
        if c == '\\' and i + 1 < length:
            i += 1
            chars.append(js_text[i])
        elif c == '[':
            in_class = True
        elif c == ']':
            in_class = False
        elif c == '/' and not in_class:
            break
        i += 1
    i += 1  # skip closing /
    # Consume flags (gimsuy)
    while i < length and js_text[i] in 'gimsuy':
        chars.append(js_text[i])
        i += 1
    return ''.join(chars), i


def _strip_js_comments(js_text):
    """Hapus komentar // dan /* */ dari JavaScript, aman untuk string, regex, dan URL."""
    result = []
    i = 0
    length = len(js_text)
    max_iterations = length * 3
    iterations = 0

    while i < length:
        iterations += 1
        if iterations > max_iterations:
            logger.warning("JS stripper: safety limit exceeded")
            return js_text

        ch = js_text[i]

        # Double-quoted string
        if ch == '"':
            result.append(ch)
            i += 1
            while i < length:
                c = js_text[i]
                result.append(c)
                if c == '\\':
                    i += 1
                    if i < length:
                        result.append(js_text[i])
                elif c == '"':
                    break
                i += 1
            i += 1
            continue

        # Single-quoted string
        if ch == "'":
            result.append(ch)
            i += 1
            while i < length:
                c = js_text[i]
                result.append(c)
                if c == '\\':
                    i += 1
                    if i < length:
                        result.append(js_text[i])
                elif c == "'":
                    break
                i += 1
            i += 1
            continue

        # Template literal
        if ch == '`':
            result.append(ch)
            i += 1
            depth = 1
            while i < length and depth > 0:
                c = js_text[i]
                result.append(c)
                if c == '\\':
                    i += 1
                    if i < length:
                        result.append(js_text[i])
                elif c == '`' and depth == 1:
                    depth -= 1
                elif c == '$' and i + 1 < length and js_text[i + 1] == '{':
                    result.append(js_text[i + 1])
                    i += 1
                    depth += 1
                elif c == '{' and depth > 1:
                    depth += 1
                elif c == '}' and depth > 1:
                    depth -= 1
                i += 1
            continue

        # Possible regex literal /pattern/flags
        if ch == '/' and i + 1 < length and js_text[i + 1] not in ('/', '*'):
            if _is_regex_context(result):
                regex_str, new_i = _consume_regex(js_text, i)
                result.append(regex_str)
                i = new_i
                continue

        # Line comment //
        if ch == '/' and i + 1 < length and js_text[i + 1] == '/':
            end = js_text.find('\n', i)
            if end == -1:
                break
            result.append('\n')
            i = end + 1
            continue

        # Block comment /* */
        if ch == '/' and i + 1 < length and js_text[i + 1] == '*':
            end = js_text.find('*/', i + 2)
            if end == -1:
                break
            newlines = js_text[i:end + 2].count('\n')
            if newlines > 0:
                result.append('\n' * newlines)
            i = end + 2
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


class HTMLCommentStripperMiddleware(MiddlewareMixin):
    """
    Menghapus semua komentar developer dari response HTML.
    Menangani: HTML <!-- -->, Django {# #}, CSS /* */, JS // dan /* */.
    """

    def process_response(self, request, response):
        if getattr(response, 'streaming', False):
            return response

        content_type = response.get('Content-Type', '')
        if 'text/html' not in content_type:
            return response

        if not hasattr(response, 'content'):
            return response

        if response.get('Content-Encoding') == 'gzip':
            return response

        try:
            content = response.content.decode('utf-8')
        except (UnicodeDecodeError, Exception):
            return response

        original = content

        # Step 1: Strip Django template comments
        try:
            content = _RE_DJANGO_COMMENT.sub('', content)
        except Exception as e:
            logger.warning("Gagal strip Django comments: %s", e)

        # Step 2: Strip HTML comments
        try:
            content = _RE_HTML_COMMENT.sub('', content)
        except Exception as e:
            logger.warning("Gagal strip HTML comments: %s", e)

        # Step 3: Strip CSS comments dalam <style>
        try:
            def strip_css(match):
                return match.group(1) + _RE_CSS_COMMENT.sub('', match.group(2)) + match.group(3)
            content = re.sub(
                r'(<style[^>]*>)(.*?)(</style>)',
                strip_css, content,
                flags=re.DOTALL | re.IGNORECASE
            )
        except Exception as e:
            logger.warning("Gagal strip CSS comments: %s", e)

        # Step 4: Strip JS comments dalam <script> (inline)
        try:
            def strip_js(match):
                js = match.group(2)
                if not js.strip():
                    return match.group(0)
                return match.group(1) + _strip_js_comments(js) + match.group(3)
            content = re.sub(
                r'(<script(?![^>]*\bsrc\b)[^>]*>)(.*?)(</script>)',
                strip_js, content,
                flags=re.DOTALL | re.IGNORECASE
            )
        except Exception as e:
            logger.warning("Gagal strip JS comments: %s", e)

        if content != original:
            response.content = content.encode('utf-8')
            if 'Content-Length' in response:
                del response['Content-Length']

        return response
