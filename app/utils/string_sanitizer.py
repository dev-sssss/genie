def sanitize_and_indent(raw_block: str, target_indentation: str) -> str:
    if not raw_block or not raw_block.strip():
        return ""
        
    lines = raw_block.split('\n')
    non_empty_lines = [line for line in lines if line.strip()]
    
    min_existing_indent = 0
    if non_empty_lines:
        indents = [len(line) - len(line.lstrip()) for line in non_empty_lines]
        min_existing_indent = min(indents)
        
    result = []
    for index, line in enumerate(lines):
        if not line.strip():
            result.append("")
        else:
            stripped_line = line[min_existing_indent:]
            if index == 0:
                result.append(stripped_line)
            else:
                result.append(target_indentation + stripped_line)
                
    return "\n".join(result)
