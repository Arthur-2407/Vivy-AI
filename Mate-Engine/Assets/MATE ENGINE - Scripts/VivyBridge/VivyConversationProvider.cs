using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;
using Vivy.Communication;

namespace Vivy.Communication
{
    [DefaultExecutionOrder(-100)]
    public class VivyConversationProvider : MonoBehaviour, IConversationProvider, IEmotionProvider, IMemoryProvider, ILLMProvider
    {
        [Header("Backend Settings")]
        public string serverBaseUrl = "http://127.0.0.1:8080";
        public float responseTimeout = 60f;

        [Header("Typewriter Stream Settings")]
        public float minWordDelay = 0.05f;
        public float maxWordDelay = 0.15f;

        private string _prompt = "You are Vivy — a real companion.";
        private int _contextSize = 4096;
        private List<ChatMessage> _cachedChatHistory = new List<ChatMessage>();
        private readonly Queue<Action> _mainThreadQueue = new Queue<Action>();

        void Awake()
        {
            // Initial caching of prompt from file if present
            try
            {
                string promptPath = GetFixedPromptPath();
                if (File.Exists(promptPath))
                {
                    _prompt = File.ReadAllText(promptPath).Trim();
                }
            }
            catch { }
            _cachedChatHistory.Add(new ChatMessage { role = "system", content = _prompt });
        }

        void Start()
        {
            // Pre-fetch history asynchronously
            StartCoroutine(FetchHistoryCoroutine());
        }

        void Update()
        {
            // Dispatch actions to main thread
            lock (_mainThreadQueue)
            {
                while (_mainThreadQueue.Count > 0)
                {
                    _mainThreadQueue.Dequeue().Invoke();
                }
            }
        }

        private void QueueOnMainThread(Action action)
        {
            lock (_mainThreadQueue)
            {
                _mainThreadQueue.Enqueue(action);
            }
        }

        // =====================================================
        // IConversationProvider
        // =====================================================
        public async Task<string> Chat(string query, Action<string> callback = null, Action completionCallback = null, bool addToHistory = true)
        {
            string receivedResponse = null;
            Action<string> onSpeak = (text) => {
                receivedResponse = text;
            };

            // Subscribe to static OnSpeakReceived event from VivyWebSocketClient
            VivyWebSocketClient.OnSpeakReceived += onSpeak;

            // Trigger POST send message in a thread-safe way
            QueueOnMainThread(() => StartCoroutine(PostSendCoroutine(query)));

            // Wait for WebSocket message to arrive
            float elapsed = 0f;
            while (receivedResponse == null && elapsed < responseTimeout)
            {
                await Task.Delay(100);
                elapsed += 0.1f;
            }

            VivyWebSocketClient.OnSpeakReceived -= onSpeak;

            if (receivedResponse == null)
            {
                Debug.LogError("[VivyBridge] Timeout waiting for reply from Vivy backend.");
                QueueOnMainThread(() => completionCallback?.Invoke());
                return null;
            }

            // Stream faked typewriter effect to the main thread UI
            var tcs = new TaskCompletionSource<bool>();
            QueueOnMainThread(() => {
                StartCoroutine(FakeStreamCoroutine(receivedResponse, callback, () => {
                    completionCallback?.Invoke();
                    tcs.SetResult(true);
                }));
            });

            await tcs.Task;
            return receivedResponse;
        }

        private IEnumerator PostSendCoroutine(string text)
        {
            string json = "{\"text\":" + JsonUtility.ToJson(text) + "}";
            using (var webRequest = new UnityWebRequest($"{serverBaseUrl}/api/send", "POST"))
            {
                byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(json);
                webRequest.uploadHandler = new UploadHandlerRaw(bodyRaw);
                webRequest.downloadHandler = new DownloadHandlerBuffer();
                webRequest.SetRequestHeader("Content-Type", "application/json");
                yield return webRequest.SendWebRequest();

                if (webRequest.result != UnityWebRequest.Result.Success)
                {
                    Debug.LogError("[VivyBridge] PostSend HTTP failed: " + webRequest.error);
                }
            }
        }

        private IEnumerator FakeStreamCoroutine(string fullText, Action<string> callback, Action doneCallback)
        {
            if (string.IsNullOrEmpty(fullText))
            {
                doneCallback?.Invoke();
                yield break;
            }

            string[] words = fullText.Split(' ');
            string currentText = "";
            for (int i = 0; i < words.Length; i++)
            {
                currentText += (i > 0 ? " " : "") + words[i];
                callback?.Invoke(currentText);
                yield return new WaitForSeconds(UnityEngine.Random.Range(minWordDelay, maxWordDelay));
            }
            callback?.Invoke(fullText);
            doneCallback?.Invoke();
        }

        // =====================================================
        // IEmotionProvider
        // =====================================================
        public string CurrentEmotion
        {
            get
            {
                var client = GetComponent<VivyWebSocketClient>();
                if (client != null && client.emotionMapper != null)
                {
                    // Fallback to reading the last mapped emotion name
                    return "neutral"; 
                }
                return "neutral";
            }
        }

        public void SetEmotion(string emotion)
        {
            var client = GetComponent<VivyWebSocketClient>();
            if (client != null && client.emotionMapper != null)
            {
                client.emotionMapper.SetEmotion(emotion);
            }
        }

        public void SetBlendshapeDirect(string name, float weight)
        {
            var client = GetComponent<VivyWebSocketClient>();
            if (client != null && client.emotionMapper != null)
            {
                client.emotionMapper.SetBlendshapeDirect(name, weight);
            }
        }

        // =====================================================
        // IMemoryProvider
        // =====================================================
        public List<ChatMessage> GetChatHistory()
        {
            // Return cached or fetch synchronously
            try
            {
                using (var client = new System.Net.WebClient())
                {
                    client.Encoding = System.Text.Encoding.UTF8;
                    string json = client.DownloadString($"{serverBaseUrl}/api/history");
                    _cachedChatHistory = ParseHistoryJson(json);
                }
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[VivyBridge] Failed to fetch chat history synchronously. Using cache: " + ex.Message);
            }
            return _cachedChatHistory;
        }

        public void AddMessage(string role, string content)
        {
            _cachedChatHistory.Add(new ChatMessage { role = role, content = content });
        }

        public void ClearChat()
        {
            _cachedChatHistory.Clear();
            _cachedChatHistory.Add(new ChatMessage { role = "system", content = Prompt });
            StartCoroutine(ClearHistoryCoroutine());
        }

        private IEnumerator ClearHistoryCoroutine()
        {
            using (var webRequest = new UnityWebRequest($"{serverBaseUrl}/api/history/clear", "POST"))
            {
                webRequest.downloadHandler = new DownloadHandlerBuffer();
                yield return webRequest.SendWebRequest();
                if (webRequest.result != UnityWebRequest.Result.Success)
                {
                    Debug.LogError("[VivyBridge] ClearHistory HTTP failed: " + webRequest.error);
                }
            }
        }

        public Task Save(string filename) => Task.CompletedTask;
        public Task Load(string filename) => Task.CompletedTask;

        private IEnumerator FetchHistoryCoroutine()
        {
            using (var webRequest = UnityWebRequest.Get($"{serverBaseUrl}/api/history"))
            {
                yield return webRequest.SendWebRequest();
                if (webRequest.result == UnityWebRequest.Result.Success)
                {
                    _cachedChatHistory = ParseHistoryJson(webRequest.downloadHandler.text);
                }
            }
        }

        [Serializable]
        private class HistoryWrapper
        {
            public List<HistoryItem> items = null;
        }
        [Serializable]
        private class HistoryItem
        {
            public string sender = "";
            public string text = "";
        }

        private List<ChatMessage> ParseHistoryJson(string json)
        {
            var list = new List<ChatMessage>();
            list.Add(new ChatMessage { role = "system", content = Prompt });

            if (string.IsNullOrEmpty(json) || json == "[]")
                return list;

            try
            {
                string wrappedJson = "{\"items\":" + json + "}";
                var wrapper = JsonUtility.FromJson<HistoryWrapper>(wrappedJson);
                if (wrapper != null && wrapper.items != null)
                {
                    foreach (var item in wrapper.items)
                    {
                        list.Add(new ChatMessage
                        {
                            role = item.sender == "user" ? "user" : "assistant",
                            content = item.text
                        });
                    }
                }
            }
            catch (Exception ex)
            {
                Debug.LogError("[VivyBridge] Failed to parse history JSON: " + ex.Message);
            }
            return list;
        }

        // =====================================================
        // ILLMProvider
        // =====================================================
        public Task Warmup(Action completionCallback = null)
        {
            completionCallback?.Invoke();
            return Task.CompletedTask;
        }

        public void CancelRequests()
        {
            // No-op
        }

        public string Prompt
        {
            get => _prompt;
            set => _prompt = value;
        }

        public void SetPrompt(string newPrompt, bool clearChat = true)
        {
            _prompt = newPrompt;
            if (clearChat) ClearChat();

            try
            {
                string promptPath = GetFixedPromptPath();
                string dir = Path.GetDirectoryName(promptPath);
                if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                File.WriteAllText(promptPath, newPrompt);
            }
            catch (Exception ex)
            {
                Debug.LogError("[VivyBridge] Failed to write system prompt to LocalLow: " + ex.Message);
            }
        }

        public int ContextSize
        {
            get => _contextSize;
            set => _contextSize = value;
        }

        private string GetFixedPromptPath()
        {
            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            var localLow = Path.GetFullPath(Path.Combine(localAppData, @"..\LocalLow"));
            var dir = Path.Combine(localLow, "Shinymoon", "MateEngineX");
            return Path.Combine(dir, "ZomeAI_prompt.txt");
        }
    }
}
