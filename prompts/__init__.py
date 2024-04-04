import tiktoken

GPT_MODEL_NAME = 'gpt-3.5-turbo'
# GPT_MODEL_NAME = "gpt-4"

def _skip_curly_brackets(content):
    return content.replace('{', '}}').replace('}', '}}')

def count_tokens_in_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.encoding_for_model(GPT_MODEL_NAME)
    num_tokens = len(encoding.encode(str(string)))
    return num_tokens

def count_tokens_in_prompt_messages(messages: list) -> int:
    """Returns the number of tokens in a list of prompt messages."""
    num_tokens = 0
    for role, content in messages:
        num_tokens += count_tokens_in_string(content)
    return num_tokens
