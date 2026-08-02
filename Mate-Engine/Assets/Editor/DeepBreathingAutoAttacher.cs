using UnityEngine;
using UnityEditor;
using Vivy.AnimationFramework;

namespace Vivy.EditorScripts
{
    public class DeepBreathingAutoAttacher : EditorWindow
    {
        [MenuItem("Vivy AI/Attach Deep Breathing System")]
        public static void AttachToAvatar()
        {
            // Find the main avatar in the scene. 
            // We assume the avatar has an Animator and possibly VivyEmotionMapper.
            Animator[] animators = UnityEngine.Object.FindObjectsByType<Animator>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            GameObject targetAvatar = null;

            foreach (Animator anim in animators)
            {
                if (anim.isHuman)
                {
                    targetAvatar = anim.gameObject;
                    break;
                }
            }

            if (targetAvatar != null)
            {
                // Check if it already has the component
                DeepBreathingAnimation existingComponent = targetAvatar.GetComponent<DeepBreathingAnimation>();
                if (existingComponent == null)
                {
                    targetAvatar.AddComponent<DeepBreathingAnimation>();
                    Debug.Log($"[Vivy AI] Successfully attached DeepBreathingAnimation to {targetAvatar.name}!");
                    Selection.activeGameObject = targetAvatar; // Select it in the hierarchy
                }
                else
                {
                    Debug.Log($"[Vivy AI] {targetAvatar.name} already has the DeepBreathingAnimation component.");
                    Selection.activeGameObject = targetAvatar;
                }
            }
            else
            {
                Debug.LogWarning("[Vivy AI] Could not find a Humanoid Avatar in the current scene to attach the breathing system to.");
            }
        }
    }
}
