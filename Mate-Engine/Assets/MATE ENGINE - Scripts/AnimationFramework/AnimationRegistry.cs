using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using Vivy.Logging;

namespace Vivy.AnimationFramework
{
    /// <summary>
    /// Data-driven Animation Registry (v1.0.0).
    /// Loads animation metadata from vivy_animation_registry.json.
    /// Provides trigger/clip lookup by emotion, category, or ID.
    /// </summary>
    public class AnimationRegistry : MonoBehaviour, IAnimationRegistry
    {
        public static AnimationRegistry Instance { get; private set; }

        public string registryFileName = "vivy_animation_registry.json";
        private RegistryData _data = new RegistryData();
        private string _fullPath;

        public string Version => _data?.version ?? "1.0.0";
        public string FallbackTrigger => _data?.fallback_trigger ?? "Idle0";

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;

            ResolvePath();
            Reload();
        }

        private void ResolvePath()
        {
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..", ".."));
            string pathInRoot = Path.Combine(projectRoot, registryFileName);
            _fullPath = File.Exists(pathInRoot) ? pathInRoot : Path.Combine(Application.persistentDataPath, registryFileName);
        }

        public void Reload()
        {
            try
            {
                if (File.Exists(_fullPath))
                {
                    string json = File.ReadAllText(_fullPath);
                    _data = JsonUtility.FromJson<RegistryData>(json) ?? new RegistryData();
                    VivyLogger.Info("AnimationRegistry", $"Loaded registry with version {_data.version} from {_fullPath}");
                }
                else
                {
                    VivyLogger.Warn("AnimationRegistry", $"Registry file not found at {_fullPath}. Using default fallback.");
                }
            }
            catch (Exception ex)
            {
                VivyLogger.Error("AnimationRegistry", $"Failed to load animation registry: {ex.Message}");
            }
        }

        public List<AnimationClipMetadata> GetAnimationsForCategory(string category)
        {
            if (_data == null || _data.categories == null || string.IsNullOrEmpty(category)) return new List<AnimationClipMetadata>();
            switch (category.ToLower().Trim())
            {
                case "idle": return _data.categories.idle;
                case "dance": return _data.categories.dance;
                case "gesture": return _data.categories.gesture;
                case "status": return _data.categories.status;
                case "face": return _data.categories.face;
                case "procedural": return _data.categories.procedural;
                case "idle_animations": return _data.categories.idle_animations;
                case "breathing_animations": return _data.categories.breathing_animations;
                case "blink_system": return _data.categories.blink_system;
                case "eye_movement": return _data.categories.eye_movement;
                case "head_movement": return _data.categories.head_movement;
                case "facial_expressions": return _data.categories.facial_expressions;
                case "mouth_animations": return _data.categories.mouth_animations;
                case "hand_gestures": return _data.categories.hand_gestures;
                case "finger_animations": return _data.categories.finger_animations;
                case "arm_animations": return _data.categories.arm_animations;
                case "shoulder_animations": return _data.categories.shoulder_animations;
                case "upper_body": return _data.categories.upper_body;
                case "sitting": return _data.categories.sitting;
                case "standing": return _data.categories.standing;
                case "walking": return _data.categories.walking;
                case "running": return _data.categories.running;
                case "jumping": return _data.categories.jumping;
                case "crouching": return _data.categories.crouching;
                case "falling": return _data.categories.falling;
                case "sleeping": return _data.categories.sleeping;
                case "dancing": return _data.categories.dancing;
                case "greeting": return _data.categories.greeting;
                case "conversation": return _data.categories.conversation;
                case "emotional_body_language": return _data.categories.emotional_body_language;
                case "romantic": return _data.categories.romantic;
                case "object_interaction": return _data.categories.object_interaction;
                case "computer_interaction": return _data.categories.computer_interaction;
                case "fitness": return _data.categories.fitness;
                case "environmental_reactions": return _data.categories.environmental_reactions;
                case "ai_specific_behaviors_vivy": return _data.categories.ai_specific_behaviors_vivy;
                case "micro_animations_procedural": return _data.categories.micro_animations_procedural;
                default: return new List<AnimationClipMetadata>();
            }
        }

        public List<string> GetTriggersForEmotion(string emotion)
        {
            if (string.IsNullOrEmpty(emotion)) return new List<string> { FallbackTrigger };
            emotion = emotion.ToLower().Trim();
            if (_data != null && _data.emotion_map != null)
            {
                switch (emotion)
                {
                    case "joy": return _data.emotion_map.joy;
                    case "sadness": return _data.emotion_map.sadness;
                    case "anger": return _data.emotion_map.anger;
                    case "surprise": return _data.emotion_map.surprise;
                    case "fear": return _data.emotion_map.fear;
                    case "disgust": return _data.emotion_map.disgust;
                    case "neutral": return _data.emotion_map.neutral;
                }
            }
            return new List<string> { FallbackTrigger };
        }

        public AnimationClipMetadata GetClipById(string clipId)
        {
            if (_data == null || string.IsNullOrEmpty(clipId)) return null;
            var all = new List<AnimationClipMetadata>();
            all.AddRange(_data.categories.idle);
            all.AddRange(_data.categories.dance);
            all.AddRange(_data.categories.gesture);
            all.AddRange(_data.categories.status);
            all.AddRange(_data.categories.face);
            all.AddRange(_data.categories.procedural);
            all.AddRange(_data.categories.idle_animations);
            all.AddRange(_data.categories.breathing_animations);
            all.AddRange(_data.categories.blink_system);
            all.AddRange(_data.categories.eye_movement);
            all.AddRange(_data.categories.head_movement);
            all.AddRange(_data.categories.facial_expressions);
            all.AddRange(_data.categories.mouth_animations);
            all.AddRange(_data.categories.hand_gestures);
            all.AddRange(_data.categories.finger_animations);
            all.AddRange(_data.categories.arm_animations);
            all.AddRange(_data.categories.shoulder_animations);
            all.AddRange(_data.categories.upper_body);
            all.AddRange(_data.categories.sitting);
            all.AddRange(_data.categories.standing);
            all.AddRange(_data.categories.walking);
            all.AddRange(_data.categories.running);
            all.AddRange(_data.categories.jumping);
            all.AddRange(_data.categories.crouching);
            all.AddRange(_data.categories.falling);
            all.AddRange(_data.categories.sleeping);
            all.AddRange(_data.categories.dancing);
            all.AddRange(_data.categories.greeting);
            all.AddRange(_data.categories.conversation);
            all.AddRange(_data.categories.emotional_body_language);
            all.AddRange(_data.categories.romantic);
            all.AddRange(_data.categories.object_interaction);
            all.AddRange(_data.categories.computer_interaction);
            all.AddRange(_data.categories.fitness);
            all.AddRange(_data.categories.environmental_reactions);
            all.AddRange(_data.categories.ai_specific_behaviors_vivy);
            all.AddRange(_data.categories.micro_animations_procedural);

            foreach (var clip in all)
            {
                if (clip.id.Equals(clipId, StringComparison.OrdinalIgnoreCase))
                    return clip;
            }
            return null;
        }

        [Serializable]
        private class RegistryData
        {
            public string version = "1.0.0";
            public CategoriesData categories = new CategoriesData();
            public EmotionMapData emotion_map = new EmotionMapData();
            public string fallback_trigger = "Idle0";
        }

        [Serializable]
        private class CategoriesData
        {
            public List<AnimationClipMetadata> idle = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> dance = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> gesture = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> status = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> face = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> procedural = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> idle_animations = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> breathing_animations = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> blink_system = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> eye_movement = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> head_movement = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> facial_expressions = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> mouth_animations = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> hand_gestures = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> finger_animations = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> arm_animations = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> shoulder_animations = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> upper_body = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> sitting = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> standing = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> walking = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> running = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> jumping = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> crouching = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> falling = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> sleeping = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> dancing = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> greeting = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> conversation = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> emotional_body_language = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> romantic = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> object_interaction = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> computer_interaction = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> fitness = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> environmental_reactions = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> ai_specific_behaviors_vivy = new List<AnimationClipMetadata>();
            public List<AnimationClipMetadata> micro_animations_procedural = new List<AnimationClipMetadata>();
        }

        [Serializable]
        private class EmotionMapData
        {
            public List<string> joy = new List<string> { "IdleHappy", "IdleCheer" };
            public List<string> sadness = new List<string> { "IdleSad" };
            public List<string> anger = new List<string> { "IdleAngry" };
            public List<string> surprise = new List<string> { "IdleSurprise" };
            public List<string> fear = new List<string>();
            public List<string> disgust = new List<string>();
            public List<string> neutral = new List<string>();
        }
    }
}
