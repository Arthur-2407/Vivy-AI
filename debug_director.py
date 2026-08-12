import sys
sys.path.insert(0, 'd:\\Vivy')
import conversation
from unittest.mock import patch
mem = conversation.load()
mem['task_state'] = {}
mem['active_task'] = None
with patch.object(conversation, 'autonomous_search_decision', return_value=(True, 'news')):
    categories = conversation.classify_message('Search the web for news.')
    print('CATEGORIES:', categories)
    state = conversation.conversation_director('Search the web for news.', [], mem, categories)
    print('DIRECTOR STATE:', state)
