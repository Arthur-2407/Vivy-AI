using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Vivy.Communication
{
    [Serializable]
    public struct ChatMessage
    {
        public string role;
        public string content;
    }

    public delegate void EmptyCallback();
    public delegate void Callback<T>(T value);

    public interface IConversationProvider
    {
        Task<string> Chat(string query, Action<string> callback = null, Action completionCallback = null, bool addToHistory = true);
    }

    public interface IEmotionProvider
    {
        string CurrentEmotion { get; }
        void SetEmotion(string emotion);
        void SetBlendshapeDirect(string name, float weight);
    }

    public interface IMemoryProvider
    {
        List<ChatMessage> GetChatHistory();
        void AddMessage(string role, string content);
        void ClearChat();
        Task Save(string filename);
        Task Load(string filename);
    }

    public interface ILLMProvider
    {
        Task Warmup(Action completionCallback = null);
        void CancelRequests();
        string Prompt { get; set; }
        void SetPrompt(string newPrompt, bool clearChat = true);
        int ContextSize { get; set; }
    }
}
