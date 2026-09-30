"""Shared query syntax; filenames use plocate, text contents use ripgrep."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

@dataclass(frozen=True)
class Query:
    name: str = ''
    extensions: tuple = ()
    date: object = None
    contains: str = ''
    error: str = ''
    strict: bool = False
    def matches(self,path,modified_ns=0,directory=False):
        if self.error:return False
        p=Path(path)
        if self.name and ((p.name!=self.name) if self.strict else (self.name.casefold() not in p.name.casefold())):return False
        if self.extensions and (directory or p.suffix.lstrip('.').casefold() not in self.extensions):return False
        if self.date and (not modified_ns or datetime.fromtimestamp(modified_ns/1e9).date()!=self.date):return False
        return True
    def patterns(self):
        # Literal filenames are escaped for plocate's glob grammar.
        literal=self.name.replace('[','[[]').replace('*','[*]').replace('?','[?]')
        if not literal and len(self.extensions)==1:return [f'*.{self.extensions[0]}']
        return [f'*{literal}*']

def parse_query(text,strict=False):
    # A quoted contains phrase can include things that resemble filter tokens.
    token=re.compile(r'(?<!\S)(is|date|contains):\s*("[^"\n]*(?:"|$)|\'[^\'\n]*(?:\'|$)|.*?)(?=\s+(?:is|date|contains):|$)',re.I)
    values={};spans=[]
    for m in token.finditer(text):
        value=m.group(2).strip()
        if len(value)>1 and value[0] in '\"\'' and value[-1]==value[0]:value=value[1:-1]
        values[m.group(1).lower()]=value;spans.append(m.span())
    plain=text
    for a,b in reversed(spans):plain=plain[:a]+' '+plain[b:]
    name=plain.strip() if strict else ' '.join(plain.split());extensions=();date=None;error=''
    if len(name)>1 and name[0] in '\"\'' and name[-1]==name[0]:name=name[1:-1]
    if 'is' in values:
        extensions=tuple(x.lower().lstrip('.') for x in re.split(r'[\s,|]+',values['is']) if x)
        if not extensions:error='After is: enter an extension, for example png or mp3.'
        elif any(not re.fullmatch(r'[a-z0-9_+-]+',x) for x in extensions):error='Use file extensions after is:, separated by commas.'
    if 'date' in values:
        try:
            if not re.fullmatch(r'\d{2}/\d{2}/\d{4}',values['date']):raise ValueError()
            date=datetime.strptime(values['date'],'%d/%m/%Y').date()
        except ValueError:error='After date: enter a modified date as dd/mm/yyyy.'
    if 'contains' in values and not values['contains']:error='After contains: enter the text to find.'
    return Query(name,extensions,date,values.get('contains',''),error,bool(strict))
