import sys
sys.path.insert(0, 'd:\\Vivy')
import conversation
from unittest.mock import patch
from verification.instrumentation.vivy_instrumentation import instrumenter
from verification.instrumentation.trace_collector import get_collector

get_collector().clear()
instrumenter.start_trace('TRACE-NO_NETWORK')

patches = []
patches.append(patch.object(conversation, 'search_duckduckgo', return_value=''))
patches.append(patch.object(conversation, 'autonomous_search_decision', return_value=(True, 'news')))
for p in patches: p.start()

try:
    mem = conversation.load()
    conversation.generate_reply_internal(
        user='Search the web for news.',
        history=[],
        mem=mem,
        perception_state={'camera_active': True}
    )
except Exception as e:
    print('EXCEPTION:', e)

instrumenter.stop_trace()
for p in patches: p.stop()

spans = get_collector().get_spans()
print('SPANS:')
for s in spans:
    print(s.get('name'), s.get('payload'))
