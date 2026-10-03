import io
import tokenize


def normalize_code(source: str) -> list[str]:
    """Convert source code into a normalized token stream."""
    tokens: list[str] = []
    stream = tokenize.generate_tokens(io.StringIO(source).readline)

    for tok in stream:
        if tok.type in {
            tokenize.COMMENT,
            tokenize.ENCODING,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENDMARKER,
        }:
            continue

        if tok.type == tokenize.NAME:
            tokens.append("ID")
        elif tok.type == tokenize.NUMBER:
            tokens.append("NUM")
        elif tok.type == tokenize.STRING:
            tokens.append("STR")
        else:
            tokens.append(tok.string)

    return tokens
