"""Read-only public HTML structure check; no full editorial text or secrets."""
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
import requests
from bs4 import BeautifulSoup
from betbot import stavka

now=pd.Timestamp.now(tz='UTC')
html=stavka.fetch(stavka.BASE+'/predictions/tennis',requests)
soup=BeautifulSoup(html,'html.parser')
print('TENNIS_OUTCOME_LABELS',dict(Counter(e.get_text(' ',strip=True) for e in soup.select('.PredictionsItem .outcome'))),flush=True)
url=next(stavka.public_url(a['href']) for a in soup.select('a.PredictionsItemEvent') if a.get('href'))
html=stavka.fetch(url,requests)
soup=BeautifulSoup(html,'html.parser')
for card in soup.select('.PredictionsItem'):card.decompose()
print('MATCH_SOURCE',url,flush=True)
print('QUOTE_CLASSES',dict(Counter(c for e in soup.select('[class]') for c in e.get('class',[]) if any(w in c.lower() for w in ('odd','rate','book','market','outcome')))),flush=True)
for node in soup.select('.MatchHeaderRates, .MatchPopularOutcomes')[:2]:
    print('QUOTE_BLOCK',str(node)[:7000],flush=True)
for node in soup.select('.Rate, .rate, .odd')[:4]:
    parent=node.parent
    print('QUOTE_STRUCTURE',str(parent)[:1800],flush=True)
