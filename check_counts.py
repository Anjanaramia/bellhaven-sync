from src.state_store import StateStore
import collections
s = StateStore()
c = collections.Counter(p['classification'] for p in s.list_pending())
print(c)