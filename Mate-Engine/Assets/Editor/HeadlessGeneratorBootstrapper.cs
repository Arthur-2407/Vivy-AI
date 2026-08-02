using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.IO;

namespace VivyAI.Editor
{
    [InitializeOnLoad]
    public class HeadlessGeneratorBootstrapper
    {
        static HeadlessGeneratorBootstrapper()
        {
            EditorApplication.delayCall += RunHeadlessOnce;
        }

        static void RunHeadlessOnce()
        {
            if (!SessionState.GetBool("HeadlessGeneratorDone_V7", false))
            {
                SessionState.SetBool("HeadlessGeneratorDone_V7", true);
                RunHeadless();
            }
        }

        public static void RunHeadless()
        {
            Debug.Log("[HeadlessGenerator] Auto-starting modernized generator...");
            string registryFilePath = "d:/Vivy/vivy_animation_registry.json";
            AnimatorController targetController = null;
            
            string[] guids = AssetDatabase.FindAssets("t:AnimatorController");
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (path.Contains("AvatarAnimatorControllerV2.controller"))
                {
                    targetController = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
                    break;
                }
            }

            if (targetController != null)
            {
                var window = ScriptableObject.CreateInstance<VivyAnimatorGenerator>();
                // Use reflection or direct call since GenerateAnimator is private.
                // We'll just temporarily make it internal or call it via reflection.
                var method = typeof(VivyAnimatorGenerator).GetMethod("GenerateAnimator", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                if (method != null)
                {
                    method.Invoke(window, new object[] { targetController, registryFilePath });
                    Debug.Log("[HeadlessGenerator] Modernization pipeline complete.");
                }
            }
        }
    }
}
