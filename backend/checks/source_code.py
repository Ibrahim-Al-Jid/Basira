"""Offline source-code checks for PHP, JavaScript/TypeScript and Python (P19).

No code is executed and nothing is installed. Each language gets a small, deliberately
conservative data-flow pass: request input is a source, a few well-known calls are sinks,
and known sanitizers or validation guards stop the flow. Findings are "review_required":
this is pattern analysis inside one file, not a proof of exploitability.

Limits (also listed in docs/checks/source-code.md):
- flow is followed inside one file only; values passed through functions or other files are lost;
- a validation guard (is_numeric, in_array, a comparison with a literal, an allowlist test)
  anywhere in the file clears that variable everywhere in the file, so the check prefers a
  missed finding over a false alarm;
- JavaScript is read with regular expressions, not a parser; Python uses the standard `ast`.
"""

import ast
import re
from pathlib import PurePosixPath

from . import config

RULE_IDS = tuple(f"SRC-{index:02d}" for index in range(1, 15))

TEXT = {
    "SRC-01": ("high", "SQL query built from request input", "استعلام SQL مبني من مدخلات الطلب",
               "Use parameterized queries or prepared statements and never concatenate request values into SQL.",
               "استخدم استعلامات مُعلَّمة أو prepared statements ولا تدمج قيم الطلب داخل نص SQL."),
    "SRC-02": ("high", "Request input reaches an operating system command", "مدخلات الطلب تصل إلى أمر نظام تشغيل",
               "Avoid the shell, pass arguments as a list, and validate against an allowlist.",
               "تجنب الـshell ومرّر الوسائط كقائمة وتحقق منها مقابل قائمة سماح."),
    "SRC-03": ("high", "Request input reaches dynamic code execution", "مدخلات الطلب تصل إلى تنفيذ كود ديناميكي",
               "Remove eval-style execution of request data and map inputs to fixed functions.",
               "احذف تنفيذ بيانات الطلب بأسلوب eval واربط المدخلات بدوال ثابتة."),
    "SRC-04": ("high", "Request input written into HTML without encoding", "مدخلات الطلب تُكتب في HTML بدون ترميز",
               "Encode output for its HTML context or use a template engine with automatic escaping.",
               "رمّز المخرجات حسب سياق HTML أو استخدم محرك قوالب بترميز تلقائي."),
    "SRC-05": ("medium", "Redirect target taken from request input", "وجهة التحويل مأخوذة من مدخلات الطلب",
               "Redirect only to relative paths or to an allowlist of destinations.",
               "حوّل فقط إلى مسارات نسبية أو إلى قائمة وجهات مسموحة."),
    "SRC-06": ("high", "File path or include built from request input", "مسار ملف أو include مبني من مدخلات الطلب",
               "Map input to a fixed set of files, or resolve the path and check it stays inside the base folder.",
               "اربط المدخل بمجموعة ملفات ثابتة أو حلّ المسار وتأكد أنه داخل المجلد الأساسي."),
    "SRC-07": ("high", "Uploaded file stored without type validation", "ملف مرفوع يُحفظ بدون التحقق من نوعه",
               "Allow only needed extensions and content types, rename the file, and store it outside the web root.",
               "اسمح بالامتدادات وأنواع المحتوى المطلوبة فقط، وغيّر اسم الملف، واحفظه خارج مجلد الويب."),
    "SRC-08": ("medium", "State-changing handler without a CSRF token check", "معالج يغيّر الحالة بدون فحص توكن CSRF",
               "Require and verify an anti-CSRF token (or SameSite cookies plus an origin check) on state-changing requests.",
               "اطلب توكن CSRF وتحقق منه (أو SameSite مع فحص الأصل) في الطلبات التي تغيّر الحالة."),
    "SRC-09": ("high", "Session or token value from a predictable source", "قيمة جلسة أو توكن من مصدر يمكن توقعه",
               "Generate identifiers with a cryptographically secure generator such as random_bytes, secrets or crypto.randomBytes.",
               "ولّد المعرّفات بمولّد آمن تشفيريًا مثل random_bytes أو secrets أو crypto.randomBytes."),
    "SRC-10": ("high", "Request input chooses the server-side request URL", "مدخلات الطلب تحدد عنوان طلب يرسله الخادم",
               "Fetch only from an allowlist of hosts and block internal addresses after DNS resolution.",
               "اجلب من قائمة مضيفين مسموحة فقط وامنع العناوين الداخلية بعد حل DNS."),
    "SRC-11": ("high", "Request input reaches unsafe deserialization", "مدخلات الطلب تصل إلى فك تسلسل غير آمن",
               "Use a data-only format such as JSON and validate it; never unserialize or unpickle request data.",
               "استخدم صيغة بيانات فقط مثل JSON مع تحقق، ولا تفك تسلسل بيانات الطلب."),
    "SRC-12": ("high", "Request input used as a template", "مدخلات الطلب تُستخدم كقالب",
               "Render fixed template files and pass request values only as template variables.",
               "اعرض ملفات قوالب ثابتة ومرّر قيم الطلب كمتغيرات فقط."),
    "SRC-13": ("medium", "Cookie set without Secure or HttpOnly", "كوكي بدون Secure أو HttpOnly",
               "Set both Secure and HttpOnly (and SameSite) when the cookie carries a session or token.",
               "فعّل Secure وHttpOnly (وSameSite) عندما يحمل الكوكي جلسة أو توكن."),
    "SRC-14": ("high", "TLS certificate verification disabled in code", "التحقق من شهادة TLS معطّل في الكود",
               "Remove the override and trust a proper certificate chain.",
               "احذف التعطيل واعتمد سلسلة شهادات صحيحة."),
}

CLASSES = frozenset({"sql", "html", "cmd", "path", "redirect", "code", "url", "deser", "tpl", "upload"})
NONE = frozenset()
UPLOAD_ONLY = frozenset({"upload", "path"})
PHP_SUFFIXES = {".php", ".phtml", ".inc", ".php5", ".php7"}
JS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
PY_SUFFIXES = {".py"}
UPLOAD_GUARD = re.compile(
    r"allowed_file|allowed_ext|ALLOWED_EXTENSIONS|\.endswith\(|splitext|mimetype|content_type|imghdr|"
    r"getimagesize|finfo|mime_content_type|fileFilter|extname|\.mime\b|pathinfo|in_array|magic\.|filetype",
    re.I)
TOKEN_WORDS = re.compile(r"csrf|xsrf|_token|checktoken|verify_token|nonce|anti.?forgery|csrfmiddleware", re.I)
PROJECT_CSRF = re.compile(r"csrf|xsrf|antiforgery|csurf|lusca", re.I)
TOKEN_NAMES = re.compile(r"token|session|sess|sid|secret|nonce|otp|csrf|reset|api_?key|passw|auth|remember", re.I)


class Results:
    def __init__(self, applicable):
        self.matches = {rule: ([] if applicable else None) for rule in RULE_IDS}
        self.seen = set()

    def add(self, rule, path, line, evidence, *, review=True):
        key = (rule, path, line)
        if key in self.seen:
            return
        self.seen.add(key)
        severity, title, title_ar, remediation, remediation_ar = TEXT[rule]
        self.matches[rule].append({
            "path": path, "line": line, "evidence": evidence, "severity": severity,
            "title": title, "title_ar": title_ar, "remediation": remediation, "remediation_ar": remediation_ar,
            "assessment": "review_required" if review else "observed", "confidence": "medium" if review else "high",
        })


# ---------------------------------------------------------------- shared text helpers

def balanced(text, open_index):
    """Index of the bracket that closes text[open_index], or -1. Skips quoted strings."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack = [pairs[text[open_index]]]
    quote = None
    index = open_index + 1
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char in pairs:
            stack.append(pairs[char])
        elif stack and char == stack[-1]:
            stack.pop()
            if not stack:
                return index
        index += 1
    return -1


def split_args(text):
    parts, depth, quote, start, index = [], 0, None, 0, 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
        index += 1
    parts.append(text[start:])
    return [part.strip() for part in parts]


def calls(text, names, *, method=True):
    """Yield (name, args_text, start_index) for each call to one of `names` in text."""
    pattern = re.compile(r"(?<![\w$])(?:(?:[\w$]+(?:->|\.|::))*)(" + "|".join(map(re.escape, names)) + r")\s*\(") \
        if method else re.compile(r"(?<![\w$>.:])(" + "|".join(map(re.escape, names)) + r")\s*\(")
    for match in pattern.finditer(text):
        end = balanced(text, match.end() - 1)
        if end < 0:
            end = len(text)
        if end > 0:
            yield match.group(1), text[match.end():end], match.start()


def blank_single_quoted(text):
    """Empty single-quoted strings (no interpolation in PHP); keep double-quoted ones."""
    return re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'",
                  lambda match: match.group(0) if match.group(0)[0] == '"' else "''", text, flags=re.S)


def scan_comments(source, line_comments, block=True, hash_comment=False):
    """Replace comments with spaces (newlines kept) so line numbers survive."""
    out, index, quote, length = [], 0, None, len(source)
    while index < length:
        char = source[index]
        pair = source[index:index + 2]
        if quote:
            out.append(char)
            if char == "\\" and index + 1 < length:
                out.append(source[index + 1])
                index += 1
            elif char == quote or (char == "\n" and quote != "`" and quote != '"'):
                quote = None
            index += 1
            continue
        if char in "'\"`":
            quote = char
            out.append(char)
        elif (pair == "//" and "//" in line_comments) or (char == "#" and hash_comment):
            while index < length and source[index] != "\n":
                out.append(" ")
                index += 1
            continue
        elif block and pair == "/*":
            end = source.find("*/", index + 2)
            end = length if end < 0 else end + 2
            out.extend(c if c == "\n" else " " for c in source[index:end])
            index = end
            continue
        else:
            out.append(char)
        index += 1
    return "".join(out)


def logical_statements(code, *, split_braces):
    """Yield (line, text). Splits on ; (and { } for PHP) outside quotes and brackets."""
    statements, buffer, depth, quote, line, start = [], [], 0, None, 1, 1
    index = 0
    while index < len(code):
        char = code[index]
        if quote:
            buffer.append(char)
            if char == "\\" and index + 1 < len(code):
                buffer.append(code[index + 1])
                if code[index + 1] == "\n":
                    line += 1
                index += 1
            elif char == quote:
                quote = None
            elif char == "\n":
                line += 1
            index += 1
            continue
        if char in "'\"`":
            quote = char
            buffer.append(char)
        elif char in "([":
            depth += 1
            buffer.append(char)
        elif char in ")]":
            depth = max(0, depth - 1)
            buffer.append(char)
        elif depth == 0 and (char == ";" or (split_braces and char in "{}")):
            text = "".join(buffer).strip()
            if text:
                statements.append((start, text))
            buffer, start = [], line
        else:
            if char == "\n":
                line += 1
                if not "".join(buffer).strip():
                    start = line
            buffer.append(char)
        index += 1
    text = "".join(buffer).strip()
    if text:
        statements.append((start, text))
    return statements


def first_line(start, text):
    """Line of the first non-blank character of a statement."""
    return start + len(text) - len(text.lstrip("\n")) if text.startswith("\n") else start


# ---------------------------------------------------------------- PHP

PHP_SOURCE = re.compile(r"\$(?:_GET|_POST|_REQUEST|_COOKIE|_FILES|__TAINT__|HTTP_RAW_POST_DATA)\b")
PHP_SANITIZERS = {
    **dict.fromkeys(["intval", "floatval", "doubleval", "abs", "count", "strlen", "md5", "sha1", "hash", "crypt",
                     "password_hash", "bin2hex", "base64_encode", "urlencode", "rawurlencode", "filter_var",
                     "is_numeric", "ctype_digit", "uniqid", "sizeof", "json_encode", "number_format",
                     "random_int", "random_bytes", "openssl_random_pseudo_bytes"], CLASSES),
    **dict.fromkeys(["mysqli_real_escape_string", "mysql_real_escape_string", "addslashes", "pg_escape_string",
                     "real_escape_string", "quote", "sqlite_escape_string", "escapeString", "esc_sql"], {"sql"}),
    **dict.fromkeys(["htmlspecialchars", "htmlentities", "strip_tags", "esc_html", "esc_attr", "e"], {"html"}),
    **dict.fromkeys(["escapeshellarg", "escapeshellcmd"], {"cmd"}),
    **dict.fromkeys(["basename", "realpath"], {"path"}),
}
PHP_GUARDS = ("is_numeric", "ctype_digit", "ctype_alnum", "ctype_alpha", "is_int", "is_integer", "in_array",
              "array_key_exists", "filter_var", "preg_match", "preg_match_all", "checkdate")
PHP_SQL_SINKS = ("mysqli_query", "mysql_query", "mysqli_multi_query", "mysqli_real_query", "pg_query", "pg_send_query",
                 "sqlite_query", "query", "exec", "multi_query", "real_query", "prepare", "get_results", "get_var",
                 "get_row", "get_col", "mssql_query", "sqlsrv_query", "oci_parse")
PHP_CMD_SINKS = ("shell_exec", "exec", "system", "passthru", "popen", "proc_open", "pcntl_exec")
PHP_RESULT_CALLS = set(PHP_SQL_SINKS + PHP_CMD_SINKS) | {"fetch", "fetch_assoc", "fetchAll", "fetchColumn", "execute",
                                                         "mysqli_fetch_assoc", "mysqli_fetch_array", "mysqli_fetch_row"}
PHP_PATH_SINKS = ("file_get_contents", "fopen", "readfile", "file", "unlink", "copy", "rename", "file_put_contents",
                  "fpassthru", "highlight_file", "show_source", "mkdir", "rmdir", "touch", "opendir", "scandir",
                  "parse_ini_file", "move_uploaded_file", "include", "include_once", "require", "require_once")
PHP_WEAK = re.compile(r"\b(?:rand|mt_rand|time|microtime|uniqid|lcg_value|date|getmypid)\s*\(")
PHP_STRONG = re.compile(r"\b(?:random_bytes|random_int|openssl_random_pseudo_bytes)\s*\(")


def php_code(source):
    """Keep only PHP regions (and `<?=`), strip comments, keep line numbers."""
    out, index = [], 0
    for match in re.finditer(r"<\?(php|=)?(.*?)(?:\?>|\Z)", source, re.S):
        out.append("".join(char for char in source[index:match.start()] if char == "\n"))
        body = match.group(2)
        out.append(("echo " if match.group(1) == "=" else "") + body + ";" if match.group(1) == "=" else body)
        index = match.end()
    out.append("".join(char for char in source[index:] if char == "\n"))
    return scan_comments("".join(out), {"//"}, True, hash_comment=True)


def php_guard_tokens(statements):
    guarded = set()
    equals = re.compile(r"((?:strtolower|strtoupper)\(\s*)?(\$\w+(?:\[[^\]]+\])*)\s*\)?\s*(?:===?|!==?)\s*['\"][^'\"]+['\"]")
    reverse = re.compile(r"['\"][^'\"]+['\"]\s*(?:===?|!==?)\s*(\$\w+(?:\[[^\]]+\])*)")
    for _, text in statements:
        for name, args, _ in calls(text, PHP_GUARDS, method=False):
            parts = split_args(args)
            target = parts[1] if name.startswith("preg_match") and len(parts) > 1 else parts[0]
            token = php_token(target)
            if token:
                guarded.add(token)
        for pattern in (equals, reverse):
            for match in pattern.finditer(text):
                guarded.add(php_token(match.group(match.lastindex if pattern is reverse else 2)))
    guarded.discard(None)
    return guarded


def php_token(text):
    text = re.sub(r"\s+", "", text.strip()).replace('"', "'")
    match = re.match(r"\$_(?:GET|POST|REQUEST|COOKIE|FILES)(?:\['\w+'\])+", text)
    if match:
        return match.group(0).replace("'", "")
    match = re.match(r"\$(\w+)", text)
    return "$" + match.group(1) if match else None


class PhpFlow:
    def __init__(self, guarded):
        self.vars, self.text, self.guarded = {}, {}, guarded
        self.weak, self.guard_names = set(), {token for token in guarded if not token.startswith("$_")}

    def prepare(self, expr):
        expr = re.sub(r"\$_SERVER\s*\[\s*['\"](?:QUERY_STRING|REQUEST_URI|PATH_INFO|PHP_SELF|HTTP_\w+)['\"]\s*\]",
                      "$__TAINT__", expr)
        expr = blank_single_quoted(expr)
        for token in self.guarded:
            if token.startswith("$_") and "[" in token:
                head, keys = token.split("[", 1)
                keys = re.findall(r"\w+", keys)
                expr = re.sub(re.escape(head) + "".join(r"\s*\[\s*['\"]?" + re.escape(key) + r"['\"]?\s*\]" for key in keys),
                              " ", expr)
        return re.sub(r"\(\s*(?:int|integer|float|double|bool|boolean)\s*\)\s*\$\w+(?:\s*\[[^\]]*\])*", " ", expr)

    def classes(self, expr, *, prepared=False):
        if not prepared:
            expr = self.prepare(expr)
        for name, args, start in calls(expr, tuple(PHP_SANITIZERS), method=True):
            end = start + expr[start:].index("(") + len(args) + 2
            call_start = expr.index("(", start)
            end = balanced(expr, call_start)
            return (self.classes(args, prepared=True) - PHP_SANITIZERS[name]) | self.classes(
                expr[:start] + " " + expr[end + 1:], prepared=True)
        result = set(CLASSES) if PHP_SOURCE.search(expr) else set()
        if "$_FILES" not in expr:
            result.discard("upload")
        for name in re.findall(r"\$(\w+)", expr):
            if "$" + name not in self.guard_names:
                result |= self.vars.get(name, NONE)
        return result

    def assign(self, lhs, op, rhs):
        name = lhs[1:].split("[")[0]
        raw = rhs
        stripped = rhs.strip().lstrip("@(").lstrip()
        call = re.match(r"(?:\$\w+(?:->\w+)*->|[\w\\]+::)?(\w+)\s*\(", stripped)
        if call and call.group(1) in PHP_RESULT_CALLS:
            new = NONE
        else:
            new = frozenset(self.classes(rhs))
        if op == ".=":
            new = new | self.vars.get(name, NONE)
            self.text[name] = self.text.get(name, "") + " " + raw
        else:
            self.text[name] = raw
        if "$" + name in self.guard_names:
            new = NONE
        self.vars[name] = frozenset(new)
        return new


def php_check(path, source, results, state):
    statements = logical_statements(php_code(source), split_braces=True)
    flow = PhpFlow(php_guard_tokens(statements))
    reads_request = False
    for start, text in statements:
        line = start
        body = re.sub(r"^\s*(?:case\b[^:]*:|default\s*:)", "", text).strip()
        for _ in range(4):
            stripped = re.match(r"\s*(?:(?:else\s*)?if|elseif|while|for|foreach|switch|catch)\s*\(", body)
            if not stripped:
                break
            end = balanced(body, stripped.end() - 1)
            if end < 0:
                break
            if stripped.group(0).strip().startswith("foreach"):
                each = re.match(r"\s*(.+?)\s+as\s+(?:\$(\w+)\s*=>\s*)?\$(\w+)\s*$", body[stripped.end():end], re.S)
                if each:
                    taint = flow.classes(each.group(1))
                    for name in each.groups()[1:]:
                        if name:
                            flow.vars[name] = frozenset(taint)
            body = body[end + 1:]
        body = re.sub(r"^\s*(?:else|try|do)\b", "", body).strip()
        prepared = flow.prepare(text)
        reads_request = reads_request or bool(PHP_SOURCE.search(prepared))
        php_sinks(path, text, prepared, line, flow, results, state)
        assign = re.match(r"(\$\w+(?:\s*\[[^\]]*\])*)\s*(\.=|=|\+=)(?!=)\s*(.+)$", body, re.S)
        if assign:
            lhs, op, rhs = assign.groups()
            new = flow.assign(lhs, op, rhs)
            raw_rhs = flow.text[lhs[1:].split("[")[0]]
            if "html" in new and re.search(r"<[a-zA-Z/]", raw_rhs if op == "=" else rhs):
                results.add("SRC-04", path, line, "PHP request input is placed into an HTML string without encoding.")
                flow.vars[lhs[1:].split("[")[0]] = frozenset(new - {"html"})
            php_weak_assign(flow, lhs, op, rhs)
        else:
            increment = re.fullmatch(r"(?:\+\+|--)?\s*(\$\w+(?:\s*\[[^\]]*\])*)\s*(?:\+\+|--)?", body)
            if increment and re.search(r"\+\+|--", body):
                key = re.match(r"\$_SESSION\s*\[\s*['\"](\w+)['\"]\s*\]", increment.group(1))
                flow.weak.add("$_SESSION[" + key.group(1) + "]" if key else increment.group(1).split("[")[0])
        echo = re.match(r"(echo|print|printf|vprintf|die|exit)\b\s*\(?(.*)$", body, re.S)
        if echo and "html" in flow.classes(echo.group(2)):
            results.add("SRC-04", path, line, "PHP request input is printed without HTML encoding.")
        php_cookie_and_weak(path, body, line, flow, results)
        for name, args, _ in calls(text, ("curl_setopt", "stream_context_create"), method=False):
            if re.search(r"CURLOPT_SSL_VERIFY(?:PEER|HOST)\s*,\s*(?:false|0)\b|verify_peer(?:_name)?['\"]?\s*=>\s*false", args, re.I):
                results.add("SRC-14", path, line, "PHP turns off TLS certificate verification.", review=False)
    php_state_change(path, statements, flow, reads_request, results, state)


def php_is_weak(expr, flow):
    """True when the value comes from a counter, the clock or a non-secure random call."""
    if PHP_STRONG.search(expr):
        return False
    plain = blank_single_quoted(expr)
    if PHP_WEAK.search(plain):
        return True
    for key in re.findall(r"\$_SESSION\s*\[\s*['\"](\w+)['\"]\s*\]", expr):
        if "$_SESSION[" + key + "]" in flow.weak:
            return True
    return any(re.search(r"\$" + re.escape(item[1:]) + r"\b", plain) for item in flow.weak if re.fullmatch(r"\$\w+", item))


def php_weak_assign(flow, lhs, op, rhs):
    name = "$" + lhs[1:].split("[")[0]
    if op == "=" and php_is_weak(rhs, flow):
        flow.weak.add(name)
    elif op == "=":
        flow.weak.discard(name)


def php_cookie_and_weak(path, body, line, flow, results):
    for name, args, _ in calls(body, ("setcookie", "setrawcookie"), method=False):
        parts = split_args(args)
        value = parts[1] if len(parts) > 1 else ""
        label = re.sub(r"['\"]", "", parts[0]) if parts else ""
        options = parts[2] if len(parts) > 2 and parts[2].lstrip().startswith(("[", "array")) else None
        if options is not None:
            secure = re.search(r"['\"]secure['\"]\s*=>\s*true", options, re.I)
            httponly = re.search(r"['\"]httponly['\"]\s*=>\s*true", options, re.I)
        else:
            secure = len(parts) > 5 and parts[5].strip().lower() not in {"false", "0", "null", ""}
            httponly = len(parts) > 6 and parts[6].strip().lower() not in {"false", "0", "null", ""}
        if parts and value.strip() and not (secure and httponly) and TOKEN_NAMES.search(label):
            results.add("SRC-13", path, line, "PHP setcookie() call without both Secure and HttpOnly.")
        if php_is_weak(value, flow) and TOKEN_NAMES.search(label + " id"):
            results.add("SRC-09", path, line, "PHP builds a cookie value from a counter, time or non-secure random source.")
    for name, args, _ in calls(body, ("session_id",), method=False):
        if args.strip() and php_is_weak(args, flow):
            results.add("SRC-09", path, line, "PHP sets the session id from a predictable value.")


def php_sinks(path, text, prepared, line, flow, results, state):
    for name, args, _ in calls(prepared, PHP_SQL_SINKS, method=True):
        parts = split_args(args)
        linked = name in {"mysqli_query", "mysqli_multi_query", "mysqli_real_query", "pg_query", "pg_send_query",
                          "sqlsrv_query", "mssql_query", "oci_parse"}
        query = parts[1] if linked and len(parts) > 1 else parts[0]
        if name in {"exec", "query", "prepare", "multi_query"} and not re.search(
                r"\b(?:select|insert|update|delete|replace|drop|create|alter|where)\b",
                query + " " + flow.text.get(re.sub(r"[^\w]", "", query), ""), re.I) and not query.lstrip().startswith("$"):
            continue
        if "sql" in flow.classes(query, prepared=True):
            results.add("SRC-01", path, line, f"PHP request input reaches {name}() inside a query string.")
        state["sql_write"].append((line, query + " " + " ".join(flow.text.get(v, "") for v in re.findall(r"\$(\w+)", query))))
    for name, args, _ in calls(prepared, PHP_CMD_SINKS, method=False):
        if "cmd" in flow.classes(args, prepared=True):
            results.add("SRC-02", path, line, f"PHP request input reaches {name}().")
    for backtick in re.findall(r"`([^`]*)`", prepared):
        if "cmd" in flow.classes(backtick, prepared=True):
            results.add("SRC-02", path, line, "PHP request input reaches a backtick shell command.")
    for name, args, _ in calls(prepared, ("eval", "assert", "create_function"), method=False):
        if "code" in flow.classes(args, prepared=True):
            results.add("SRC-03", path, line, f"PHP request input reaches {name}().")
    for name, args, _ in calls(prepared, ("call_user_func", "call_user_func_array"), method=False):
        if "code" in flow.classes(split_args(args)[0], prepared=True):
            results.add("SRC-03", path, line, f"PHP request input chooses the function called by {name}().")
    include = re.match(r"\s*(?:@\s*)?(include_once|include|require_once|require)\b\s*\(?(.*)$", text, re.S)
    if include and "path" in flow.classes(include.group(2)):
        results.add("SRC-06", path, line, f"PHP {include.group(1)} path comes from request input.")
    for name, args, _ in calls(prepared, PHP_PATH_SINKS[:-4], method=False):
        parts = split_args(args)
        target = parts[1] if name in {"move_uploaded_file", "copy", "rename"} and len(parts) > 1 else parts[0]
        if name == "move_uploaded_file":
            if re.search(r"\$_FILES|\$\w+", parts[0]) and not state["upload_guard"]:
                results.add("SRC-07", path, line, "PHP move_uploaded_file() with no extension or content-type validation in the file.")
            continue
        if "path" in flow.classes(target, prepared=True) and not re.search(r"['\"]https?://", target):
            results.add("SRC-06", path, line, f"PHP request input reaches the path argument of {name}().")
    for name, args, _ in calls(prepared, ("file_get_contents", "fopen", "curl_init", "get_headers", "simplexml_load_file"), method=False):
        first = split_args(args)[0]
        if "url" in flow.classes(first, prepared=True) and re.match(r"\s*\$", first):
            results.add("SRC-10", path, line, f"PHP request input is the URL passed to {name}().")
    for name, args, _ in calls(prepared, ("curl_setopt",), method=False):
        parts = split_args(args)
        if len(parts) > 2 and "CURLOPT_URL" in parts[1] and re.match(r"\s*\$", parts[2]) and "url" in flow.classes(parts[2], prepared=True):
            results.add("SRC-10", path, line, "PHP request input is the URL set with CURLOPT_URL.")
    for name, args, _ in calls(prepared, ("unserialize",), method=False):
        if "deser" in flow.classes(split_args(args)[0], prepared=True):
            results.add("SRC-11", path, line, "PHP request input reaches unserialize().")
    for name, args, _ in calls(prepared, ("header",), method=False):
        first = split_args(args)[0]
        location = re.match(r"\s*[\"']?\s*location\s*:(.*)$", re.sub(r"\s+", " ", text[text.find(args):]).strip() and first, re.I | re.S)
        raw_first = first
        if re.match(r"[\"']\s*location\s*:", raw_first.strip(), re.I) or re.match(r"[\"']\s*location\s*:", re.sub(r"'", "'", text[text.find("header"):]).split("(", 1)[-1].strip(), re.I):
            if "redirect" in flow.classes(first, prepared=True):
                results.add("SRC-05", path, line, "PHP Location header is built from request input.")
    for name, args, _ in calls(prepared, ("wp_redirect",), method=False):
        if "redirect" in flow.classes(args, prepared=True):
            results.add("SRC-05", path, line, "PHP redirect target is built from request input.")


def php_state_change(path, statements, flow, reads_request, results, state):
    if not reads_request or state["csrf_token"]:
        return
    for line, query in state["sql_write"]:
        if re.search(r"\b(?:insert\s+into|update\s+\S+\s+set|delete\s+from|replace\s+into)\b", query, re.I):
            results.add("SRC-08", path, line, "PHP handler writes to the database from request data and the file never checks a token.")
            return


# ---------------------------------------------------------------- JavaScript / TypeScript

JS_SOURCE = re.compile(
    r"\b(?:req|request|ctx)\.(?:query|body|params|headers|cookies|files|file|url|originalUrl|path|hostname|signedCookies)\b"
    r"|\blocation\.(?:search|hash|href|pathname)\b|\bdocument\.(?:URL|documentURI|referrer|cookie|location)\b"
    r"|\bwindow\.(?:name|location)\b|\bevent\.data\b")
JS_SANITIZERS = {
    **dict.fromkeys(["parseInt", "parseFloat", "Number", "Boolean", "encodeURIComponent", "encodeURI", "escape",
                     "randomUUID", "randomBytes", "isInteger"], CLASSES),
    **dict.fromkeys(["escapeHtml", "escapeHTML", "sanitize", "sanitizeHtml", "xss", "encode", "escapeText", "clean"], {"html"}),
    **dict.fromkeys(["escapeId"], {"sql"}),
    **dict.fromkeys(["basename"], {"path"}),
    **dict.fromkeys(["shellEscape", "quote"], {"cmd"}),
}
JS_QUERY_STRONG = ("query", "execute", "queryRawUnsafe", "$queryRawUnsafe", "executeRawUnsafe", "$executeRawUnsafe", "raw")
JS_QUERY_WEAK = ("all", "run", "get", "each", "exec", "prepare")
JS_SQL_WORDS = re.compile(r"\b(?:select|insert\s+into|update\s+\w+\s+set|delete\s+from|drop\s+table|where)\b", re.I)


def js_code(source):
    return scan_comments(source, {"//"}, True)


def js_blank(expr):
    """Blank '...' and "..." strings, keep template-literal interpolations."""
    expr = re.sub(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"", '""', expr)
    return re.sub(r"`((?:\\.|[^`\\])*)`", lambda m: " " + " ".join(re.findall(r"\$\{([^}]*)\}", m.group(1))) + " ", expr)


def js_guard_tokens(code):
    guarded = set()
    ident = r"([\w$]+(?:\.[\w$]+)*)"
    for pattern in (
        r"\.(?:includes|has|indexOf|test|startsWith)\(\s*" + ident,
        r"\b(?:Number\.isInteger|Number\.isFinite|isNaN|isNumeric|isInt|isUUID|isEmail|validator\.\w+)\(\s*" + ident,
        ident + r"\s*(?:===?|!==?)\s*['\"][^'\"]+['\"]",
        r"['\"][^'\"]+['\"]\s*(?:===?|!==?)\s*" + ident,
        ident + r"\.startsWith\(",
        r"\bnew URL\(\s*" + ident,
    ):
        guarded.update(match.group(1) for match in re.finditer(pattern, code))
    return {token for token in guarded if token not in {"req", "res", "request", "response"}}


class JsFlow:
    def __init__(self, guarded):
        self.vars, self.text, self.guarded = {}, {}, guarded

    def classes(self, expr, *, prepared=False):
        if not prepared:
            expr = js_blank(expr)
            for token in self.guarded:
                if "." in token:
                    expr = re.sub(r"(?<![\w$.])" + re.escape(token) + r"(?![\w$])", " ", expr)
        for name, args, start in calls(expr, tuple(JS_SANITIZERS), method=True):
            end = balanced(expr, expr.index("(", start))
            return (self.classes(args, prepared=True) - JS_SANITIZERS[name]) | self.classes(
                expr[:start] + " " + expr[end + 1:], prepared=True)
        result = set(CLASSES - {"upload"}) if JS_SOURCE.search(expr) else set()
        if re.search(r"\b(?:req|request)\.files?\b", expr):
            result.add("upload")
        for name in re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)", expr):
            if name not in self.guarded:
                result |= self.vars.get(name, NONE)
        return result


def js_lines(code):
    """Join physical lines while brackets are open, unless a line ends a block opener."""
    out, buffer, start, depth = [], "", 0, 0
    for number, text in enumerate(code.split("\n"), 1):
        if not buffer:
            start = number
        buffer += text + "\n"
        depth = 0
        quote = None
        for char in buffer:
            if quote:
                if char == quote:
                    quote = None
            elif char in "'\"`":
                quote = char
            elif char in "([":
                depth += 1
            elif char in ")]":
                depth -= 1
        tail = text.rstrip()
        if depth > 0 and not tail.endswith(("{", "=>")):
            continue
        out.append((start, buffer))
        buffer = ""
    if buffer:
        out.append((start, buffer))
    return out


def js_check(path, source, results, state):
    code = js_code(source)
    flow = JsFlow(js_guard_tokens(code))
    upload_seen = False
    for start, chunk in js_lines(code):
        for segment_line, segment in logical_statements(chunk, split_braces=False):
            line = start + segment_line - 1
            text = segment
            handled = re.match(r"\s*(?:export\s+)?(?:const|let|var)\s*\{([^}]*)\}\s*=\s*(.+)$", text, re.S)
            if handled:
                taint = flow.classes(handled.group(2))
                for item in handled.group(1).split(","):
                    name = item.split(":")[-1].split("=")[0].strip()
                    if name:
                        flow.vars[name] = frozenset(taint)
            else:
                assign = re.match(r"\s*(?:export\s+)?(?:(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)(?:\s*:\s*[\w<>\[\]|.]+)?\s*(\+=|=)(?!=)\s*(.+)$", text, re.S)
                if assign:
                    name, op, rhs = assign.groups()
                    call = re.match(r"\s*(?:await\s+)?(?:[\w$]+\.)*(query|execute|exec|run|all|get|execSync|readFile|readFileSync|fetch|json)\s*\(", rhs)
                    new = NONE if call and not rhs.lstrip().startswith("await req") and call.group(1) != "json" and "req" not in rhs.split("(")[0] else frozenset(js_flow_classes(flow, rhs))
                    if op == "+=":
                        new |= flow.vars.get(name, NONE)
                    flow.vars[name] = frozenset(new)
                    flow.text[name] = (flow.text.get(name, "") + " " if op == "+=" else "") + rhs
                    js_weak(path, name, rhs, line, results)
            js_sinks(path, text, line, flow, results, state)
            upload_seen = upload_seen or bool(re.search(r"\bmulter\s*\(|\bfileUpload\s*\(|\.mv\s*\(", text))
            if re.search(r"\b(?:multer|formidable)\s*\(", text) and not UPLOAD_GUARD.search(source) and not state["upload_guard"]:
                results.add("SRC-07", path, line, "JavaScript upload handler is configured without a file type filter.")
            if re.search(r"\.mv\s*\(", text) and re.search(r"\b(?:req|request)\.files\b|\bfile\b", text) and not UPLOAD_GUARD.search(source):
                results.add("SRC-07", path, line, "JavaScript saves an uploaded file with no extension or content-type validation in the file.")
    js_state_change(path, code, results, state)


def js_flow_classes(flow, rhs):
    return flow.classes(rhs)


def js_weak(path, name, rhs, line, results):
    if TOKEN_NAMES.search(name) and re.search(r"Math\.random\s*\(|Date\.now\s*\(|new Date\(\)\.getTime\s*\(", rhs) \
            and not re.search(r"crypto\.|randomBytes|randomUUID|getRandomValues", rhs):
        results.add("SRC-09", path, line, "JavaScript builds a token-like value from Math.random or the clock.")


def js_sinks(path, text, line, flow, results, state):
    blanked = js_blank(text)
    for name, args, _ in calls(text, JS_QUERY_STRONG + JS_QUERY_WEAK, method=True):
        parts = split_args(args)
        if not parts or not parts[0]:
            continue
        first = parts[0]
        expanded = first + " " + " ".join(flow.text.get(v, "") for v in re.findall(r"[A-Za-z_$][\w$]*", first))
        if name in JS_QUERY_WEAK and not JS_SQL_WORDS.search(expanded):
            continue
        if name in JS_QUERY_STRONG and name == "query" and not JS_SQL_WORDS.search(expanded) and not re.fullmatch(r"[A-Za-z_$][\w$]*", first.strip()):
            continue
        if "sql" in flow.classes(first):
            results.add("SRC-01", path, line, f"JavaScript request input reaches .{name}() inside a query string.")
        if JS_SQL_WORDS.search(expanded):
            state["sql_write"].append((line, expanded))
    for name, args, _ in calls(text, ("exec", "execSync"), method=True):
        if "cmd" in flow.classes(split_args(args)[0]):
            results.add("SRC-02", path, line, f"JavaScript request input reaches {name}().")
    for name, args, _ in calls(text, ("spawn", "spawnSync", "execFile", "execFileSync"), method=True):
        parts = split_args(args)
        if len(parts) > 2 and re.search(r"shell\s*:\s*true", " ".join(parts[2:])) and "cmd" in flow.classes(parts[0] + parts[1]):
            results.add("SRC-02", path, line, f"JavaScript request input reaches {name}() with a shell.")
    for name, args, _ in calls(text, ("eval", "Function", "runInNewContext", "runInThisContext", "runInContext"), method=True):
        if "code" in flow.classes(args):
            results.add("SRC-03", path, line, f"JavaScript request input reaches {name}().")
    for match in re.finditer(r"\.(?:innerHTML|outerHTML)\s*(\+?=)(?!=)\s*(.+)$", blanked_keep(text), re.S):
        if "html" in flow.classes(match.group(2)):
            results.add("SRC-04", path, line, "JavaScript request or URL data is assigned to innerHTML or outerHTML.")
    for name, args, _ in calls(text, ("write", "writeln", "insertAdjacentHTML", "html", "append", "prepend", "after", "before"), method=True):
        if name in {"write", "writeln"} and not re.search(r"\bdocument\.write", text) and not re.search(r"\b(?:res|response)\.write\(", text):
            continue
        if name in {"html", "append", "prepend", "after", "before"} and not re.search(r"\$\(|jQuery\(", text):
            continue
        target = args if name != "insertAdjacentHTML" else (split_args(args) + [""])[1]
        if "html" in flow.classes(target):
            results.add("SRC-04", path, line, f"JavaScript request or URL data reaches {name}() as markup.")
    for name, args, _ in calls(text, ("send", "end", "write"), method=True):
        if re.search(r"\b(?:res|response)\s*\.\s*(?:status\(\d+\)\s*\.)?(?:send|end|write)\s*\(", text) and re.search(r"<[a-zA-Z/]", args) \
                and "html" in flow.classes(args):
            results.add("SRC-04", path, line, "JavaScript response body mixes HTML with request input and no encoding.")
    if re.search(r"dangerouslySetInnerHTML\s*=\s*\{\{?\s*__html\s*:", text):
        inner = text[text.index("__html"):]
        if "html" in flow.classes(inner.split(":", 1)[1]):
            results.add("SRC-04", path, line, "React dangerouslySetInnerHTML receives request or URL data.")
    for name, args, _ in calls(text, ("redirect", "replace", "assign"), method=True):
        if name in {"replace", "assign"} and not re.search(r"\blocation\s*\.\s*(?:replace|assign)\(", text):
            continue
        parts = split_args(args)
        target = parts[-1] if name == "redirect" and len(parts) > 1 and re.fullmatch(r"\d+", parts[0]) is None and parts[-1] else parts[0]
        if name == "redirect" and len(parts) > 1 and re.fullmatch(r"\d+", parts[0]):
            target = parts[1]
        if "redirect" in flow.classes(target) and re.match(r"\s*[\w$.\[\]'\"`]+\s*$|\s*`\$\{", target) or (
                "redirect" in flow.classes(target) and not re.match(r"\s*['\"`]/", target)):
            results.add("SRC-05", path, line, f"JavaScript redirect target comes from request or URL data ({name}).")
    for match in re.finditer(r"\b(?:window\.|document\.)?location(?:\.href)?\s*=(?!=)\s*(.+)$", text, re.S):
        if "redirect" in flow.classes(match.group(1)):
            results.add("SRC-05", path, line, "JavaScript sets the browser location from request or URL data.")
    for match in re.finditer(r"(?:setHeader|header|set)\s*\(\s*['\"]location['\"]\s*,\s*(.+)\)", text, re.I | re.S):
        if "redirect" in flow.classes(match.group(1)):
            results.add("SRC-05", path, line, "JavaScript Location header is built from request data.")
    for name, args, _ in calls(text, ("readFile", "readFileSync", "createReadStream", "writeFile", "writeFileSync", "unlink",
                                      "unlinkSync", "sendFile", "download", "readdir", "readdirSync", "rm", "rmSync", "createWriteStream"), method=True):
        first = split_args(args)[0]
        if "path" in flow.classes(first) and re.search(r"\bfs\b|\bres\b|\bfsp\b|promises|\bresponse\b", text):
            results.add("SRC-06", path, line, f"JavaScript request input reaches the path argument of {name}().")
    for name, args, _ in calls(text, ("get", "post", "put", "delete", "request", "fetch", "axios", "got", "head", "patch"), method=True):
        if name in {"get", "post", "put", "delete", "head", "patch", "request"} and not re.search(r"\b(?:axios|got|http|https|needle|superagent|request|client|fetch)\b", text[:text.find(name)]):
            continue
        first = split_args(args)[0]
        if first and re.match(r"\s*`?\$?\{?[A-Za-z_$]|\s*(?:req|request)\.", first) and "url" in flow.classes(first) and \
                re.match(r"\s*(?:`\$\{[^}]*\}|[\w$.]+\s*$|[\w$.]+\s*\+)", first):
            results.add("SRC-10", path, line, f"JavaScript request input chooses the URL passed to {name}().")
    for name, args, _ in calls(text, ("unserialize", "deserialize"), method=True):
        if "deser" in flow.classes(args) and re.search(r"serialize", text):
            results.add("SRC-11", path, line, f"JavaScript request input reaches {name}().")
    for name, args, _ in calls(text, ("render", "compile", "renderString", "template"), method=True):
        if re.search(r"\b(?:ejs|pug|jade|handlebars|Handlebars|nunjucks|mustache|Mustache|_|lodash|dot)\b", text[:text.find(name)]) \
                and "tpl" in flow.classes(split_args(args)[0]) and not re.match(r"\s*['\"]", split_args(args)[0]):
            results.add("SRC-12", path, line, f"JavaScript request input is compiled or rendered as a template ({name}).")
    for name, args, _ in calls(text, ("cookie",), method=True):
        parts = split_args(args)
        if re.search(r"\b(?:res|response|ctx\.cookies)\b", text) and len(parts) >= 2 and TOKEN_NAMES.search(re.sub(r"['\"`]", "", parts[0])):
            options = " ".join(parts[2:])
            if not (re.search(r"httpOnly\s*:\s*true", options) and re.search(r"secure\s*:\s*(?!false)", options)):
                results.add("SRC-13", path, line, "JavaScript sets a session-like cookie without both httpOnly and secure.")
    if re.search(r"rejectUnauthorized\s*:\s*false|strictSSL\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*(?:=|\]\s*=)\s*['\"]?0", text):
        results.add("SRC-14", path, line, "JavaScript turns off TLS certificate verification.", review=False)
    if re.search(r"\bsession\s*\(", text) and re.search(r"cookie\s*:\s*\{[^}]*(?:httpOnly\s*:\s*false|secure\s*:\s*false)", text):
        results.add("SRC-13", path, line, "express-session cookie options disable httpOnly or secure.")
    if re.search(r"\b(?:Math\.random)\b", blanked) and TOKEN_NAMES.search(text.split("=")[0] if "=" in text else "") is None:
        pass


def blanked_keep(text):
    return re.sub(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"", lambda m: m.group(0), text)


def js_state_change(path, code, results, state):
    if state["project_csrf"] or TOKEN_WORDS.search(code):
        return
    uses_cookies = re.search(r"express-session|cookie-session|cookieParser|req\.session|req\.cookies|session\s*\(", code)
    for match in re.finditer(r"\b(?:app|router|server)\.(?:post|put|patch|delete)\s*\(", code):
        if uses_cookies:
            line = code.count("\n", 0, match.start()) + 1
            results.add("SRC-08", path, line, "JavaScript state-changing route uses cookie sessions and no CSRF token check appears in the project.")
            return


# ---------------------------------------------------------------- Python (ast)

PY_SOURCE_ATTR = {"args", "form", "values", "json", "cookies", "headers", "files", "data", "GET", "POST", "COOKIES",
                  "META", "body", "FILES", "view_args", "query_params", "path_params", "stream", "environ"}
PY_SANITIZERS = {
    **dict.fromkeys(["int", "float", "bool", "len", "hash", "sha256", "md5", "hexdigest", "uuid4", "token_hex",
                     "token_urlsafe", "isdigit", "isnumeric", "ord"], CLASSES),
    **dict.fromkeys(["escape", "html_escape", "clean", "linkify", "strip_tags", "conditional_escape", "format_html"], {"html"}),
    **dict.fromkeys(["quote", "shlex_quote"], {"cmd"}),
    **dict.fromkeys(["secure_filename", "basename", "get_valid_filename"], {"path"}),
    **dict.fromkeys(["quote_plus", "urlencode"], CLASSES),
}
PY_SQL_SINKS = {"execute", "executemany", "executescript", "raw", "extra", "read_sql", "read_sql_query", "text",
                "RawSQL", "mogrify", "execute_sql"}
PY_GUARD_NAMES = re.compile(r"safe_url|allowed_host|is_safe|validate|is_valid|allowed|sanitize_path|check_path", re.I)
PY_NUMERIC_METHODS = {"isdigit", "isnumeric", "isalnum", "isalpha", "isdecimal", "startswith", "endswith", "fullmatch", "match"}
PY_WEAK_RANDOM = {"random", "randint", "choice", "choices", "randrange", "getrandbits", "shuffle", "sample"}


def dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def literal_text(node):
    parts = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            parts.append(child.value)
    return " ".join(parts)


class PyScope:
    def __init__(self, tainted_params=(), upload=False):
        self.vars = {name: set(CLASSES - {"upload"}) for name in tainted_params}
        self.guarded = set()
        self.text = {}


def py_names(node):
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def py_guards(function_node):
    guarded = set()
    for node in ast.walk(function_node):
        if isinstance(node, ast.Compare):
            names = py_names(node)
            if any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops) or any(
                    isinstance(side, ast.Constant) and isinstance(side.value, (str, int)) for side in [node.left, *node.comparators]):
                guarded |= names
        if isinstance(node, ast.Call):
            name = dotted(node.func).split(".")[-1]
            if PY_GUARD_NAMES.search(name) or name in PY_NUMERIC_METHODS or name in {"fullmatch", "match"}:
                for argument in [*node.args, getattr(node.func, "value", None)]:
                    if argument is not None:
                        guarded |= py_names(argument)
    return guarded


def py_classes(node, scope):
    if node is None:
        return set()
    if isinstance(node, ast.Constant):
        return set()
    if isinstance(node, ast.Name):
        return set() if node.id in scope.guarded else set(scope.vars.get(node.id, ()))
    if isinstance(node, (ast.Attribute, ast.Subscript)):
        root = node
        while isinstance(root, (ast.Attribute, ast.Subscript, ast.Call)):
            root = root.func if isinstance(root, ast.Call) else root.value
        chain = dotted(node.value if isinstance(node, ast.Subscript) else node)
        if isinstance(root, ast.Name) and root.id in {"request", "flask.request"} or chain.startswith(("request.", "flask.request.")):
            attribute = chain.split(".")[1] if "." in chain else ""
            if attribute in PY_SOURCE_ATTR or attribute == "":
                return set(CLASSES - ({"upload"} if attribute != "files" else set()))
        if chain in {"sys.argv", "os.environ"}:
            return set()
        inner = node.value
        return py_classes(inner, scope)
    if isinstance(node, ast.JoinedStr):
        result = set()
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                result |= py_classes(value.value, scope)
        return result
    if isinstance(node, ast.BinOp):
        return py_classes(node.left, scope) | py_classes(node.right, scope)
    if isinstance(node, ast.Call):
        name = dotted(node.func).split(".")[-1]
        full = dotted(node.func)
        if full in {"input", "raw_input"}:
            return set(CLASSES - {"upload"})
        if full.startswith(("request.get_json", "request.get_data", "request.args.get", "request.form.get",
                            "request.values.get", "request.GET.get", "request.POST.get", "request.cookies.get",
                            "request.headers.get")):
            return set(CLASSES - {"upload"})
        if name in PY_SANITIZERS and (name not in {"escape"} or True):
            inner = set()
            for argument in [*node.args, *[kw.value for kw in node.keywords]]:
                inner |= py_classes(argument, scope)
            if isinstance(node.func, ast.Attribute) and name in {"isdigit", "isnumeric"}:
                inner |= py_classes(node.func.value, scope)
            return inner - PY_SANITIZERS[name]
        if name in PY_SQL_SINKS or name in {"fetchone", "fetchall", "fetchmany", "check_output", "check_call", "getoutput", "popen", "system"}:
            return set()
        result = set()
        if isinstance(node.func, ast.Attribute):
            result |= py_classes(node.func.value, scope)
        for argument in [*node.args, *[kw.value for kw in node.keywords]]:
            result |= py_classes(argument, scope)
        return result
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        result = set()
        for element in node.elts:
            result |= py_classes(element, scope)
        return result
    if isinstance(node, ast.Dict):
        result = set()
        for element in node.values:
            result |= py_classes(element, scope)
        return result
    if isinstance(node, ast.IfExp):
        return py_classes(node.body, scope) | py_classes(node.orelse, scope)
    if isinstance(node, (ast.Await, ast.Starred)):
        return py_classes(node.value, scope)
    if isinstance(node, ast.BoolOp):
        result = set()
        for element in node.values:
            result |= py_classes(element, scope)
        return result
    return set()


def py_is_route(function):
    for decorator in function.decorator_list:
        text = dotted(decorator.func if isinstance(decorator, ast.Call) else decorator)
        if re.search(r"(?:^|\.)(?:route|get|post|put|delete|patch|websocket|api_view|require_http_methods)$", text):
            return True
    return False


def py_route_params(function):
    names = []
    arguments = function.args
    for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]:
        if argument.arg in {"self", "cls", "request", "req"}:
            continue
        annotation = dotted(argument.annotation) if argument.annotation is not None else ""
        if annotation in {"int", "float", "bool", "UUID", "uuid.UUID"}:
            continue
        names.append(argument.arg)
    return names


def py_check(path, source, results, state):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return False
    module_scope = PyScope()
    py_walk(path, tree.body, module_scope, results, state, route=False, source=source)
    return True


def py_walk(path, body, scope, results, state, *, route, source):
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_route = py_is_route(node)
            django_view = bool(node.args.args) and node.args.args[0].arg == "request"
            inner = PyScope(py_route_params(node) if is_route or django_view else (), False)
            inner.guarded = py_guards(node)
            inner.vars.update({k: set(v) for k, v in scope.vars.items() if k not in inner.vars and k.isupper() is False and False})
            exempt = any(re.search(r"csrf_exempt|csrf\.exempt|exempt", dotted(d.func if isinstance(d, ast.Call) else d)) for d in node.decorator_list)
            if exempt and not state["project_csrf_never"]:
                results.add("SRC-08", path, node.lineno, "Python view is explicitly exempted from CSRF protection.", review=False)
            py_walk(path, node.body, inner, results, state, route=is_route or django_view, source=source)
            continue
        if isinstance(node, ast.ClassDef):
            py_walk(path, node.body, scope, results, state, route=route, source=source)
            continue
        py_statement(path, node, scope, results, state, route=route)
        for field in ("body", "orelse", "finalbody"):
            nested = getattr(node, field, None)
            if isinstance(nested, list) and nested and not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                py_walk(path, nested, scope, results, state, route=route, source=source)
        for handler in getattr(node, "handlers", []):
            py_walk(path, handler.body, scope, results, state, route=route, source=source)


def py_statement(path, node, scope, results, state, *, route):
    targets, value = [], None
    if isinstance(node, ast.Assign):
        targets, value = node.targets, node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        targets, value = [node.target], node.value
    elif isinstance(node, ast.AugAssign):
        targets, value = [node.target], node.value
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        taint = py_classes(node.iter, scope)
        for name in py_names(node.target):
            scope.vars[name] = set(taint)
    if value is not None:
        taint = py_classes(value, scope)
        for target in targets:
            for name in ([target.id] if isinstance(target, ast.Name) else sorted(py_names(target))):
                if isinstance(node, ast.AugAssign):
                    taint |= scope.vars.get(name, set())
                scope.vars[name] = set(taint)
                scope.text[name] = literal_text(value)
            py_weak_assignment(path, target, value, node.lineno, results)
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            py_call(path, child, scope, results, state)
    if isinstance(node, ast.Return) and node.value is not None and route:
        text = literal_text(node.value)
        if "html" in py_classes(node.value, scope) and re.search(r"<[a-zA-Z/]", text):
            results.add("SRC-04", path, node.lineno, "Python view returns HTML built from request input without escaping.")
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr in {"check_hostname"} and isinstance(node.value, ast.Constant) and node.value.value is False:
                results.add("SRC-14", path, node.lineno, "Python turns off TLS hostname checking.", review=False)
            if isinstance(target, ast.Attribute) and target.attr == "verify_mode" and "CERT_NONE" in dotted(node.value):
                results.add("SRC-14", path, node.lineno, "Python turns off TLS certificate verification.", review=False)


def py_weak_assignment(path, target, value, line, results):
    name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else (
        target.slice.value if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str) else "")
    if name and TOKEN_NAMES.search(str(name)) and py_weak_source(value):
        results.add("SRC-09", path, line, "Python derives a token-like value from the random module or the clock.")


def py_weak_source(value):
    if value is None:
        return False
    for child in ast.walk(value):
        if isinstance(child, ast.Call):
            full = dotted(child.func)
            if full.startswith(("secrets.", "os.urandom", "SystemRandom", "random.SystemRandom")) or "SystemRandom" in full:
                return False
    for child in ast.walk(value):
        if isinstance(child, ast.Call):
            full = dotted(child.func)
            head, _, last = full.rpartition(".")
            if (head in {"random", "rnd"} and last in PY_WEAK_RANDOM) or full in {"time.time", "uuid.uuid1", "uuid1", "time.time_ns"}:
                return True
    return False


def py_call(path, call, scope, results, state):
    full = dotted(call.func)
    name = full.split(".")[-1]
    arguments = list(call.args)
    keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
    first = arguments[0] if arguments else None
    if name in PY_SQL_SINKS and first is not None and (name != "text" or "sqlalchemy" in state["text"] or True):
        if name == "text" and not re.search(r"\b(?:select|insert|update|delete|where)\b", literal_text(first) + " " + " ".join(
                scope.text.get(n, "") for n in py_names(first)), re.I):
            pass
        elif name == "execute" and isinstance(first, ast.Name) and False:
            pass
        elif "sql" in py_classes(first, scope):
            results.add("SRC-01", path, call.lineno, f"Python request input reaches {name}() inside a query string.")
        sql_text = literal_text(first) + " " + " ".join(scope.text.get(n, "") for n in py_names(first))
        if re.search(r"\b(?:insert\s+into|update\s+\w+\s+set|delete\s+from)\b", sql_text, re.I):
            state["sql_write"].append((call.lineno, sql_text))
    shell = keywords.get("shell")
    if full in {"os.system", "os.popen", "commands.getoutput", "subprocess.getoutput", "subprocess.getstatusoutput"} or (
            full.startswith("subprocess.") and isinstance(shell, ast.Constant) and shell.value is True) or (
            full.startswith("asyncio.create_subprocess_shell")):
        if first is not None and "cmd" in py_classes(first, scope):
            results.add("SRC-02", path, call.lineno, f"Python request input reaches {full}().")
    if full in {"eval", "exec", "compile", "builtins.eval", "builtins.exec"} and first is not None and "code" in py_classes(first, scope):
        results.add("SRC-03", path, call.lineno, f"Python request input reaches {full}().")
    if name in {"Markup", "mark_safe", "HttpResponse", "make_response", "HTMLResponse", "SafeString"} and first is not None:
        if "html" in py_classes(first, scope) and (name in {"Markup", "mark_safe", "SafeString", "HTMLResponse"} or isinstance(first, (ast.Name, ast.Attribute, ast.Subscript, ast.Call, ast.JoinedStr, ast.BinOp))):
            if name in {"make_response"} and not re.search(r"<[a-zA-Z/]", literal_text(first)):
                pass
            elif name == "HttpResponse" and not isinstance(first, ast.Constant) and not (
                    re.search(r"<[a-zA-Z/]", literal_text(first)) or isinstance(first, (ast.Name, ast.Subscript, ast.Attribute, ast.Call))):
                pass
            else:
                results.add("SRC-04", path, call.lineno, f"Python request input reaches {name}() without escaping.")
    if name in {"redirect", "HttpResponseRedirect", "RedirectResponse", "HttpResponsePermanentRedirect"} and first is not None:
        if "redirect" in py_classes(first, scope) and not (isinstance(first, ast.Call) and dotted(first.func).split(".")[-1] in {"url_for", "reverse"}):
            results.add("SRC-05", path, call.lineno, f"Python redirect target comes from request input ({name}).")
    if name in {"open", "send_file", "FileResponse", "remove", "unlink", "rmtree", "listdir", "copy", "move", "read_text", "write_text", "read_bytes", "send_from_directory"} and arguments:
        target = arguments[1] if name == "send_from_directory" and len(arguments) > 1 else first
        if name != "send_from_directory" and "path" in py_classes(target, scope) and (
                full in {"open", "io.open", "os.remove", "os.unlink", "shutil.rmtree", "os.listdir", "shutil.copy", "shutil.move"}
                or name in {"send_file", "FileResponse"} or full.endswith(("Path", "read_text", "write_text"))):
            results.add("SRC-06", path, call.lineno, f"Python request input reaches the path argument of {name}().")
    if name == "save" and isinstance(call.func, ast.Attribute) and "upload" in py_classes(call.func.value, scope) | (
            {"upload"} if re.search(r"request\.files", ast.unparse(call.func.value)) else set()):
        if not state["upload_guard"]:
            results.add("SRC-07", path, call.lineno, "Python saves an uploaded file with no extension or content-type validation in the file.")
    if full.split(".")[0] in {"requests", "httpx", "aiohttp", "session", "client", "urllib"} or full.endswith(("urlopen", "urlretrieve")):
        if name in {"get", "post", "put", "delete", "head", "patch", "request", "urlopen", "urlretrieve", "fetch"} and arguments:
            target = arguments[1] if name == "request" and len(arguments) > 1 else first
            if "url" in py_classes(target, scope) and py_url_controlled(target, scope):
                results.add("SRC-10", path, call.lineno, f"Python request input chooses the URL passed to {name}().")
    if full in {"pickle.loads", "pickle.load", "cPickle.loads", "marshal.loads", "jsonpickle.decode", "dill.loads", "shelve.open"} and first is not None:
        if "deser" in py_classes(first, scope):
            results.add("SRC-11", path, call.lineno, f"Python request input reaches {full}().")
    if full in {"yaml.load", "yaml.unsafe_load", "yaml.full_load"} and first is not None and "deser" in py_classes(first, scope):
        loader = dotted(keywords.get("Loader")) if keywords.get("Loader") is not None else (dotted(arguments[1]) if len(arguments) > 1 else "")
        if full == "yaml.unsafe_load" or "Safe" not in loader:
            results.add("SRC-11", path, call.lineno, "Python request input reaches yaml.load() without a safe loader.")
    if name in {"render_template_string", "from_string", "Template"} and first is not None and not isinstance(first, ast.Constant):
        if "tpl" in py_classes(first, scope) and (name != "Template" or full in {"Template", "jinja2.Template", "mako.template.Template"}):
            results.add("SRC-12", path, call.lineno, f"Python request input is used as a template ({name}).")
    if name == "set_cookie" and arguments:
        flags = {kw: keywords.get(kw) for kw in ("secure", "httponly")}
        good = all(isinstance(flags[k], ast.Constant) and flags[k].value is True or (flags[k] is not None and not isinstance(flags[k], ast.Constant)) for k in flags)
        label = arguments[0].value if isinstance(arguments[0], ast.Constant) and isinstance(arguments[0].value, str) else keywords.get("key")
        label = label if isinstance(label, str) else (label.value if isinstance(label, ast.Constant) else "")
        if not good and TOKEN_NAMES.search(str(label or "")):
            results.add("SRC-13", path, call.lineno, "Python set_cookie() call for a session-like cookie without both secure and httponly.")
    verify = keywords.get("verify")
    if isinstance(verify, ast.Constant) and verify.value is False and full.split(".")[0] in {"requests", "httpx", "session", "client", "s"}:
        results.add("SRC-14", path, call.lineno, "Python request call sets verify=False.", review=False)
    if full in {"ssl._create_unverified_context", "ssl._create_default_https_context"} and name == "_create_unverified_context":
        results.add("SRC-14", path, call.lineno, "Python creates an unverified TLS context.", review=False)
    if full.endswith("CERT_NONE") or (isinstance(call.func, ast.Attribute) and False):
        pass


def py_url_controlled(node, scope):
    """The request value is the whole URL or its start, not only a query or path piece."""
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)):
        return True
    if isinstance(node, ast.JoinedStr) and node.values:
        head = node.values[0]
        return isinstance(head, ast.FormattedValue)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return py_url_controlled(node.left, scope) and not isinstance(node.left, ast.Constant)
    return False


# ---------------------------------------------------------------- entry point

def language(path):
    suffix = PurePosixPath(path).suffix.lower()
    name = PurePosixPath(path).name.lower()
    if suffix in PHP_SUFFIXES:
        return "php"
    if suffix in JS_SUFFIXES and not name.endswith((".min.js", ".d.ts", ".bundle.js")):
        return "js"
    if suffix in PY_SUFFIXES:
        return "py"
    return None


def check(text_inputs, har, policy, advisories):
    """Return all SRC rule IDs: None when no PHP, JavaScript or Python file was submitted."""
    selected = {}
    for path, content in text_inputs.items():
        parts = PurePosixPath(path).parts
        kind = language(path)
        if not kind or "fixtures" in parts or config.path_selected(path, config.config_list(policy, "fixture_paths")):
            continue
        if len(content) > 400_000 or any(len(line) > 4000 for line in content.split("\n", 400)[:400]):
            continue
        selected[path] = (kind, content)
    results = Results(bool(selected))
    project_csrf = any(PROJECT_CSRF.search(scan_comments(text, {"//"}, True, hash_comment=(kind == "py")))
                       for kind, text in selected.values())
    for path, (kind, content) in selected.items():
        state = {"sql_write": [], "upload_guard": bool(UPLOAD_GUARD.search(scan_comments(content, {"//"}, True, kind == "py"))),
                 "csrf_token": bool(TOKEN_WORDS.search(scan_comments(content, {"//"}, True, kind == "py"))) or project_csrf,
                 "project_csrf": project_csrf, "project_csrf_never": False, "text": content}
        try:
            if kind == "php":
                php_check(path, content, results, state)
            elif kind == "js":
                js_check(path, content, results, state)
            else:
                py_check(path, content, results, state)
        except (RecursionError, ValueError, IndexError, KeyError, AttributeError, TypeError):
            continue
        if kind in {"js", "py"} and not state["csrf_token"] and state["sql_write"] and kind == "py":
            pass
    return results.matches
