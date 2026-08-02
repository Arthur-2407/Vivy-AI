import re
import os

path = 'd:/Vivy/templates/index.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Inject CSS
css_injection = """        /* HIDDEN BY VIVY HYPERPUMP (Phase 4) */
        #home-emotion-pill, #chat-emotion-pill, #card-cog-emotion,
        #home-affection-pill, #card-cog-affection,
        #home-circadian-pill, #card-cog-circadian,
        #home-brain-pill, #chat-brain-pill,
        #home-gpu-pill {
            display: none !important;
        }
    </style>"""
content = content.replace('    </style>', css_injection)

# 2. Inject Template
template_injection = """<body>
    <template id="live-indicator-template">
        <div class="status-glass-pill live-thinking-pill" style="display:none;" title="">
            <span style="font-size:14px;" class="live-status-icon"></span>
            <span class="pill-label">Live:</span>
            <span class="pill-value live-status-text"></span>
            <span class="live-dots-container">
                <span class="live-dot"></span>
                <span class="live-dot"></span>
                <span class="live-dot"></span>
            </span>
        </div>
    </template>"""
content = content.replace('<body>', template_injection, 1)

# 3. Replace the 4 duplicated HTML blocks with containers
def repl(m):
    pill_id = m.group(1)
    # The IDs are e.g. home-live-status-pill, chat-live-status-pill
    prefix = pill_id.split('-live')[0]
    return f'<div id="{prefix}-live-container"></div>'

pattern = r'<div class="status-glass-pill live-thinking-pill" id="(.*?)"[\s\S]*?</div>\s*</div>'
# wait, there's a </div> at the end of the pill, so:
# <div ...>
#   <span ...
# </div>
# The regex without greedy match is better:
pattern2 = r'<div class="status-glass-pill live-thinking-pill" id="([a-z\-]+)"[\s\S]*?</div>'

content = re.sub(pattern2, repl, content)

# 4. Inject JS Initialization script at the very top of <script>
js_injection = """    <script>
        function initializeLiveIndicators() {
            const containers = [
                { cid: 'home-live-container', id: 'home-live-status-pill', iconId: 'home-live-status-icon', textId: 'home-live-status-text', title: 'Live Thinking & Internal State Indicator' },
                { cid: 'chat-live-container', id: 'chat-live-status-pill', iconId: 'chat-live-status-icon', textId: 'chat-live-status-text', title: 'Live Thinking & Internal State Indicator' },
                { cid: 'voice-live-container', id: 'voice-live-status-pill', iconId: 'voice-live-status-icon', textId: 'voice-live-status-text', title: 'Live Voice Pipeline Status' },
                { cid: 'screen-live-container', id: 'screen-live-status-pill', iconId: 'screen-live-status-icon', textId: 'screen-live-status-text', title: 'Live Screen Perception Status' }
            ];
            const template = document.getElementById('live-indicator-template');
            containers.forEach(cfg => {
                const container = document.getElementById(cfg.cid);
                if (container && template) {
                    const clone = template.content.cloneNode(true);
                    const pill = clone.querySelector('.status-glass-pill');
                    const icon = clone.querySelector('.live-status-icon');
                    const text = clone.querySelector('.live-status-text');
                    pill.id = cfg.id;
                    pill.title = cfg.title;
                    icon.id = cfg.iconId;
                    text.id = cfg.textId;
                    container.appendChild(clone);
                }
            });
        }
        initializeLiveIndicators();
"""
content = content.replace('    <script>', js_injection, 1)

# 5. Fix applyOrbState MUTED
old_muted = """            } else if (status === "muted") {
                homePulseOrb.classList.add("muted");
                label = "MUTED";
                statusText = "Mic Disabled";
            }"""
new_muted = """            } else if (status === "muted") {
                homePulseOrb.classList.add("ready");
                label = "READY";
                statusText = "Vivy is ready (Mic Muted)";
            }"""
content = content.replace(old_muted, new_muted)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Modification complete.")
