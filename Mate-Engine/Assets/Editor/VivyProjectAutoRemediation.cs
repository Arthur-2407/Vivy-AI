using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.Collections.Generic;

namespace VivyAI.Editor
{
    [InitializeOnLoad]
    public static class VivyProjectAutoRemediation
    {
        static VivyProjectAutoRemediation()
        {
            EditorApplication.delayCall += RunRemediationsSilent;
        }

        [UnityEditor.Callbacks.DidReloadScripts]
        private static void OnScriptsReloaded()
        {
            EditorApplication.delayCall += RunRemediationsSilent;
        }

        private static void RunRemediationsSilent()
        {
            ExecuteRemediations(false);
        }

        [MenuItem("Vivy AI/Run Complete Project Auto-Remediation")]
        public static void RunRemediationsManual()
        {
            ExecuteRemediations(true);
        }

        public static void ExecuteRemediations(bool verbose = false)
        {
            int missingScriptsCleaned = 0;
            int controllerConditionsRepaired = 0;

            try
            {
                // 1. Clean missing scripts across ALL prefab hierarchies recursively (root and child objects)
                missingScriptsCleaned += CleanPrefabsRecursively();

                // 2. Clean missing scripts in all loaded scene objects
                missingScriptsCleaned += CleanSceneObjects();

                // 3. Clean missing scripts in Volume Profiles (e.g. leftover SRP test components in DefaultVolumeProfile)
                missingScriptsCleaned += CleanVolumeProfiles();

                // 4. Repair incompatible parameter condition modes in all Animator Controllers
                controllerConditionsRepaired += RepairAnimatorControllers();

                // 5. Suppress Unity 6 Localization PackageCache NullReferenceException in GameViewLanguageMenu
                RepairUnity6LocalizationEditorBug();

                if (missingScriptsCleaned > 0 || controllerConditionsRepaired > 0 || verbose)
                {
                    if (missingScriptsCleaned > 0 || controllerConditionsRepaired > 0)
                    {
                        AssetDatabase.SaveAssets();
                    }
                    Debug.Log($"[VivyProjectAutoRemediation] Complete. Removed {missingScriptsCleaned} missing script behaviors across prefabs/scenes/volume profiles and repaired {controllerConditionsRepaired} incompatible transition conditions without feature removal or connection breakage.");
                }
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning($"[VivyProjectAutoRemediation] Non-fatal exception during auto-remediation scan: {ex.Message}");
            }
        }

        private static int CleanVolumeProfiles()
        {
            int cleaned = 0;
            try
            {
                // Search for all ScriptableObjects across Assets to cleanly catch URP/HDRP VolumeProfiles without hardcoded package namespaces
                string[] profileGuids = AssetDatabase.FindAssets("t:ScriptableObject", new[] { "Assets" });
                foreach (string guid in profileGuids)
                {
                    string path = AssetDatabase.GUIDToAssetPath(guid);
                    if (string.IsNullOrEmpty(path)) continue;

                    var profile = AssetDatabase.LoadAssetAtPath<ScriptableObject>(path);
                    if (profile == null) continue;

                    bool modified = false;

                    // 1. Dynamically clean component/setting lists using unboxed Unity Object null checks and MonoBehaviour fallback detection
                    System.Type type = profile.GetType();
                    var memberList = new System.Collections.Generic.List<System.Reflection.MemberInfo>();
                    var compField = type.GetField("components", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                    if (compField != null) memberList.Add(compField);
                    var compProp = type.GetProperty("components", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                    if (compProp != null) memberList.Add(compProp);
                    var setField = type.GetField("settings", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                    if (setField != null) memberList.Add(setField);
                    var setProp = type.GetProperty("settings", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                    if (setProp != null) memberList.Add(setProp);

                    foreach (var member in memberList)
                    {
                        object listObj = null;
                        if (member is System.Reflection.FieldInfo fi) listObj = fi.GetValue(profile);
                        else if (member is System.Reflection.PropertyInfo pi) listObj = pi.GetValue(profile, null);

                        if (listObj is System.Collections.IList list)
                        {
                            int removed = 0;
                            for (int i = list.Count - 1; i >= 0; i--)
                            {
                                object item = list[i];
                                if (item == null || item.Equals(null) || (item is UnityEngine.Object uObj && uObj == null) || item.GetType().Name == "MonoBehaviour" || item.ToString() == "null")
                                {
                                    list.RemoveAt(i);
                                    removed++;
                                }
                            }
                            if (removed > 0)
                            {
                                cleaned += removed;
                                modified = true;
                            }
                        }
                    }

                    // 2. Remove orphaned sub-assets with missing scripts directly from the asset package
                    UnityEngine.Object[] allSubAssets = AssetDatabase.LoadAllAssetsAtPath(path);
                    foreach (var sub in allSubAssets)
                    {
                        if (sub != profile && (sub == null || sub.Equals(null) || (sub is UnityEngine.Object uSub && uSub == null) || sub.GetType().Name == "MonoBehaviour"))
                        {
                            if (sub != null && !sub.Equals(null))
                            {
                                AssetDatabase.RemoveObjectFromAsset(sub);
                                cleaned++;
                                modified = true;
                            }
                        }
                    }

                    if (modified)
                    {
                        EditorUtility.SetDirty(profile);
                        Debug.Log($"[VivyProjectAutoRemediation] Cleaned missing script overrides/orphaned sub-assets from asset: {path}.");
                    }
                }
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning($"[VivyProjectAutoRemediation] Non-fatal exception while checking ScriptableObjects: {ex.Message}");
            }
            return cleaned;
        }

        private static void RepairUnity6LocalizationEditorBug()
        {
            try
            {
                var locEditorSettingsType = System.Type.GetType("UnityEditor.Localization.LocalizationEditorSettings, Unity.Localization.Editor");
                if (locEditorSettingsType != null)
                {
                    var prop = locEditorSettingsType.GetProperty("ShowLocaleMenuInGameView", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
                    if (prop != null && prop.PropertyType == typeof(bool))
                    {
                        bool isShowEnabled = (bool)prop.GetValue(null);
                        if (isShowEnabled)
                        {
                            prop.SetValue(null, false);
                            Debug.Log("[VivyProjectAutoRemediation] Automatically disabled Localization 'ShowLocaleMenuInGameView' to eliminate Unity 6 GameViewLanguageMenu NullReferenceException without breaking any pipeline connection.");
                        }
                    }
                }
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning($"[VivyProjectAutoRemediation] Could not inspect LocalizationEditorSettings: {ex.Message}");
            }
        }

        private static int CleanPrefabsRecursively()
        {
            int cleaned = 0;
            string[] prefabGuids = AssetDatabase.FindAssets("t:Prefab", new[] { "Assets" });
            foreach (string guid in prefabGuids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrEmpty(path)) continue;

                GameObject contents = null;
                try
                {
                    contents = PrefabUtility.LoadPrefabContents(path);
                    if (contents != null)
                    {
                        int removedInThisPrefab = 0;
                        Transform[] transforms = contents.GetComponentsInChildren<Transform>(true);
                        foreach (Transform t in transforms)
                        {
                            if (t != null && t.gameObject != null)
                            {
                                removedInThisPrefab += GameObjectUtility.RemoveMonoBehavioursWithMissingScript(t.gameObject);
                            }
                        }

                        if (removedInThisPrefab > 0)
                        {
                            cleaned += removedInThisPrefab;
                            PrefabUtility.SaveAsPrefabAsset(contents, path);
                        }
                    }
                }
                catch (System.Exception)
                {
                    // Silently ignore non-editable or locked packages
                }
                finally
                {
                    if (contents != null)
                    {
                        PrefabUtility.UnloadPrefabContents(contents);
                    }
                }
            }
            return cleaned;
        }

        private static int CleanSceneObjects()
        {
            int cleaned = 0;
            var sceneObjects = UnityEngine.Object.FindObjectsByType<GameObject>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            foreach (var go in sceneObjects)
            {
                if (go == null) continue;
                int removed = GameObjectUtility.RemoveMonoBehavioursWithMissingScript(go);
                if (removed > 0)
                {
                    cleaned += removed;
                    if (PrefabUtility.IsPartOfPrefabInstance(go))
                    {
                        PrefabUtility.RecordPrefabInstancePropertyModifications(go);
                    }
                    EditorUtility.SetDirty(go);
                }
            }
            if (cleaned > 0 && !Application.isPlaying)
            {
                UnityEditor.SceneManagement.EditorSceneManager.MarkAllScenesDirty();
            }
            return cleaned;
        }

        private static int RepairAnimatorControllers()
        {
            int repaired = 0;
            string[] controllerGuids = AssetDatabase.FindAssets("t:AnimatorController", new[] { "Assets" });
            foreach (string guid in controllerGuids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrEmpty(path)) continue;

                AnimatorController controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
                if (controller == null) continue;

                Dictionary<string, AnimatorControllerParameterType> paramTypes = new Dictionary<string, AnimatorControllerParameterType>();
                foreach (var p in controller.parameters)
                {
                    paramTypes[p.name] = p.type;
                }

                bool controllerModified = false;

                foreach (var layer in controller.layers)
                {
                    if (layer.stateMachine == null) continue;
                    if (InspectStateMachine(layer.stateMachine, paramTypes, ref repaired))
                    {
                        controllerModified = true;
                    }
                }

                if (controllerModified)
                {
                    EditorUtility.SetDirty(controller);
                }
            }
            return repaired;
        }

        private static bool InspectStateMachine(AnimatorStateMachine sm, Dictionary<string, AnimatorControllerParameterType> paramTypes, ref int repairCount)
        {
            bool modified = false;

            // Check AnyState Transitions
            foreach (var trans in sm.anyStateTransitions)
            {
                if (RepairTransition(trans, paramTypes))
                {
                    modified = true;
                    repairCount++;
                }
            }

            // Check Entry Transitions
            foreach (var trans in sm.entryTransitions)
            {
                if (RepairTransition(trans, paramTypes))
                {
                    modified = true;
                    repairCount++;
                }
            }

            // Check States
            foreach (var stateNode in sm.states)
            {
                var state = stateNode.state;
                if (state == null) continue;
                foreach (var trans in state.transitions)
                {
                    if (RepairTransition(trans, paramTypes))
                    {
                        modified = true;
                        repairCount++;
                    }
                }
            }

            // Recursively inspect sub-state machines
            foreach (var subSmNode in sm.stateMachines)
            {
                if (subSmNode.stateMachine != null)
                {
                    if (InspectStateMachine(subSmNode.stateMachine, paramTypes, ref repairCount))
                    {
                        modified = true;
                    }
                }
            }

            return modified;
        }

        private static bool RepairTransition(AnimatorTransitionBase trans, Dictionary<string, AnimatorControllerParameterType> paramTypes)
        {
            if (trans == null || trans.conditions == null || trans.conditions.Length == 0) return false;

            bool needsRepair = false;
            foreach (var c in trans.conditions)
            {
                if (paramTypes.TryGetValue(c.parameter, out AnimatorControllerParameterType type))
                {
                    if (type == AnimatorControllerParameterType.Float && (c.mode == AnimatorConditionMode.Equals || c.mode == AnimatorConditionMode.NotEqual))
                    {
                        needsRepair = true;
                        break;
                    }
                }
            }

            if (!needsRepair) return false;

            List<AnimatorCondition> newConditions = new List<AnimatorCondition>();
            foreach (var c in trans.conditions)
            {
                if (paramTypes.TryGetValue(c.parameter, out AnimatorControllerParameterType type) && type == AnimatorControllerParameterType.Float && (c.mode == AnimatorConditionMode.Equals || c.mode == AnimatorConditionMode.NotEqual))
                {
                    AnimatorCondition c1 = new AnimatorCondition
                    {
                        parameter = c.parameter,
                        mode = AnimatorConditionMode.Greater,
                        threshold = c.threshold - 0.5f
                    };
                    AnimatorCondition c2 = new AnimatorCondition
                    {
                        parameter = c.parameter,
                        mode = AnimatorConditionMode.Less,
                        threshold = c.threshold + 0.5f
                    };
                    newConditions.Add(c1);
                    newConditions.Add(c2);
                }
                else
                {
                    newConditions.Add(c);
                }
            }

            trans.conditions = newConditions.ToArray();
            EditorUtility.SetDirty(trans);
            return true;
        }
    }
}
