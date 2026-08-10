import os
import re

INDEX_PATH = r"d:\Vivy\templates\index.html"
with open(INDEX_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# EXTRACT
vh_panel_start = content.find('<div id="vh-panel-voices"')
vh_panel_end = content.find('<!-- VOICE PREVIEW MODAL -->')
vh_panel_voices = content[vh_panel_start:vh_panel_end].strip()

preview_modal_start = content.find('<!-- VOICE PREVIEW MODAL -->')
preview_modal_end = content.find('<!-- SUB-TAB 2: CLONE & UPLOAD -->')
voice_preview_modal = content[preview_modal_start:preview_modal_end].strip()

if not vh_panel_voices or not voice_preview_modal:
    print("Failed to extract active voices HTML.")
    exit(1)

# CREATE NEW TAB VOICE
new_tab_voice = f"""
        <!-- ==================== TAB PANEL: VOICE ==================== -->
        <div class="tab-panel" id="tab-voice">
            <div style="display:flex; flex-direction:column; gap:16px; padding:20px; max-width:1200px; margin:0 auto; width:100%;">
                {vh_panel_voices}

                {voice_preview_modal}
            </div>
        </div>
"""

# REPLACE old tab voice
tab_voice_start = content.find('<!-- ==================== TAB PANEL: VOICE ==================== -->')
tab_voice_end = content.find('<!-- ==================== TAB PANEL: SCREEN SHARING ==================== -->')
content = content[:tab_voice_start] + new_tab_voice + "\n\n        " + content[tab_voice_end:]

# REMOVE original vh-panel-voices from cloning tab
# Since we already extracted them, we need to find where they originally were in the updated `content` string
# Wait, let's just slice it out from tab-cloning.
cloning_tab_start = content.find('<!-- ==================== TAB PANEL: VOICE CLONING ==================== -->')
cloning_tab_end = content.find('<!-- ==================== TAB PANEL: ANIMATION AUTHORING ==================== -->')
cloning_tab_content = content[cloning_tab_start:cloning_tab_end]

# In cloning_tab_content, we must remove the vh_panel_voices and voice_preview_modal
# We can just remove the substring from <div id="vh-panel-voices" to <!-- SUB-TAB 2: CLONE & UPLOAD -->
remove_start = cloning_tab_content.find('<div id="vh-panel-voices"')
remove_end = cloning_tab_content.find('<!-- SUB-TAB 2: CLONE & UPLOAD -->')
if remove_start != -1 and remove_end != -1:
    cloning_tab_content = cloning_tab_content[:remove_start] + cloning_tab_content[remove_end:]
    content = content[:cloning_tab_start] + cloning_tab_content + content[cloning_tab_end:]
else:
    print("Warning: could not find active voices in cloning tab to remove")

# 2. Remove 'Active Voices' button
content = re.sub(
    r'<button class="header-tab-btn(?: active)?" id="btn-vh-voices".*?Active Voices</button>\s*',
    '',
    content
)

# 3. Update switchVoiceHubTab JS
content = content.replace("['voices', 'upload', 'train', 'settings']", "['upload', 'train', 'settings']")
content = content.replace("if (tab === 'voices') fetchVoiceProfiles();\n", "")
content = content.replace("switchVoiceHubTab('voices');", "window.switchTab('tab-voice');")

# 4. Update window.switchTab JS
old_switch_tab_voice = """            } else if (targetTab === 'tab-voice') {
                fetchTranscripts();
                if (typeof loadMemory === 'function') loadMemory();"""
new_switch_tab_voice = """            } else if (targetTab === 'tab-voice') {
                if (typeof fetchVoiceProfiles === 'function') fetchVoiceProfiles();"""
content = content.replace(old_switch_tab_voice, new_switch_tab_voice)

# 5. Remove unused JS variables for memory/transcripts
content = re.sub(r'const memoryName = document\.getElementById\(\'memory-name\'\);.*?\n', '', content)
content = re.sub(r'const memoryHumor = document\.getElementById\(\'memory-humor\'\);.*?\n', '', content)
content = re.sub(r'const memoryPlayful = document\.getElementById\(\'memory-playful\'\);.*?\n', '', content)
content = re.sub(r'const humorVal = document\.getElementById\(\'humor-val\'\);.*?\n', '', content)
content = re.sub(r'const playfulVal = document\.getElementById\(\'playful-val\'\);.*?\n', '', content)
content = re.sub(r'const likesContainer = document\.getElementById\(\'likes-container\'\);.*?\n', '', content)
content = re.sub(r'const dislikesContainer = document\.getElementById\(\'dislikes-container\'\);.*?\n', '', content)
content = re.sub(r'const addLikeInput = document\.getElementById\(\'add-like-input\'\);.*?\n', '', content)
content = re.sub(r'const addDislikeInput = document\.getElementById\(\'add-dislike-input\'\);.*?\n', '', content)
content = re.sub(r'const memoryTone = document\.getElementById\(\'memory-tone\'\);.*?\n', '', content)
content = re.sub(r'const memoryArc = document\.getElementById\(\'memory-arc\'\);.*?\n', '', content)
content = re.sub(r'const saveMemoryBtn = document\.getElementById\(\'save-memory-btn\'\);.*?\n', '', content)
content = re.sub(r'const transcriptsBox = document\.getElementById\(\'transcripts-box\'\);.*?\n', '', content)
content = re.sub(r'let memoryData = \{ likes: \[\], dislikes: \[\] \};.*?\n', '', content)
content = re.sub(r'// Memory Profile\s*', '', content)

# 6. Remove memory functions (renderTagChips, removeTag, loadMemory, saveMemoryBtn listener)
content = re.sub(r'// Render tag chips for likes/dislikes.*?// Sliders Listeners', '// Sliders Listeners', content, flags=re.DOTALL)
content = re.sub(r'// Sliders Listeners.*?// Sync Memory Parameters', '// Sync Memory Parameters', content, flags=re.DOTALL)
content = re.sub(r'// Sync Memory Parameters.*?// Fetch pipeline statuses', '// Fetch pipeline statuses', content, flags=re.DOTALL)
content = re.sub(r'// Load Memory Matrix.*?// Sync Memory Parameters', '// Fetch pipeline statuses', content, flags=re.DOTALL)

# Let's cleanly remove fetchTranscripts
content = re.sub(r'// Fetch whisper transcript history.*?// Load Toggle Config Toggles', '// Load Toggle Config Toggles', content, flags=re.DOTALL)

# Let's cleanly remove loadMemory if it exists further down
content = re.sub(r'async function loadMemory\(\) \{.*?\n        \}\n', '', content, flags=re.DOTALL)
content = content.replace("loadMemory();\n", "")

with open(INDEX_PATH, "w", encoding="utf-8") as f:
    f.write(content)
print("Migration in index.html completed properly.")
