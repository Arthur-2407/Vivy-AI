using System.Collections.Generic;
using Vivy.Contracts;

namespace Vivy.AnimationFramework
{
    public interface IAnimationRegistry
    {
        string Version { get; }
        List<AnimationClipMetadata> GetAnimationsForCategory(string category);
        List<string> GetTriggersForEmotion(string emotion);
        AnimationClipMetadata GetClipById(string clipId);
        string FallbackTrigger { get; }
        void Reload();
    }

    [System.Serializable]
    public class AnimationClipMetadata
    {
        public string id = "";
        public string trigger = "";
        public string bool_param = "";
        public string index_param = "";
        public int index_val = 0;
        public string layer = "Base Layer";
        public float weight = 1.0f;
        public int priority = 0;
        public float duration = 0.0f;
    }
}
