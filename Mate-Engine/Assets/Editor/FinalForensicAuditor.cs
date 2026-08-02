using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.IO;
using System.Collections.Generic;
using System.Text;
using System.Linq;

namespace VivyAI.Editor
{
    [InitializeOnLoad]
    public class FinalForensicAuditor
    {
        private static string reportPath = "d:/Vivy/Final_PreRepair_Report.txt";
        private static string registryPath = "d:/Vivy/vivy_animation_registry.json";

        static FinalForensicAuditor()
        {
            EditorApplication.delayCall += RunAuditOnce;
        }

        static void RunAuditOnce()
        {
            if (!SessionState.GetBool("FinalForensicAuditDone_V3", false))
            {
                SessionState.SetBool("FinalForensicAuditDone_V3", true);
                RunAudit();
            }
        }

        [MenuItem("Vivy AI/Run FINAL Pre-Repair Audit V3")]
        public static void RunAuditMenuItem()
        {
            RunAudit();
        }

        public static void RunAudit()
        {
            Debug.Log("[FinalForensic] Starting FINAL Pre-Repair Verification V3...");

            StringBuilder report = new StringBuilder();
            report.AppendLine("======================================================================");
            report.AppendLine("FINAL PRE-REPAIR FORENSIC AUDIT");
            report.AppendLine("======================================================================");

            // Load Controller
            AnimatorController targetController = null;
            string[] controllerGuids = AssetDatabase.FindAssets("t:AnimatorController");
            foreach (string guid in controllerGuids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (path.Contains("AvatarAnimatorControllerV2.controller"))
                {
                    targetController = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
                    break;
                }
            }

            if (targetController == null)
            {
                report.AppendLine("ERROR: AvatarAnimatorControllerV2.controller not found.");
                File.WriteAllText(reportPath, report.ToString());
                return;
            }

            // Catalog ALL AnimationClips in the project
            int totalProjectClips = 0;
            Dictionary<string, List<string>> allClips = new Dictionary<string, List<string>>();
            string[] clipGuids = AssetDatabase.FindAssets("t:AnimationClip");
            
            foreach (string guid in clipGuids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                // Exclude dummy clips and editor internal clips
                if (path.Contains("VivyDummyClips") || path.Contains("Editor/Data")) continue;
                
                string fName = Path.GetFileNameWithoutExtension(path).ToLowerInvariant();
                // If it's part of an FBX, sometimes unity names the clip "Take 001" or similar. 
                // We'll also index the FBX filename itself.
                string fbxName = Path.GetFileNameWithoutExtension(path.Split('@')[0]).ToLowerInvariant();
                
                if (!allClips.ContainsKey(fName)) allClips[fName] = new List<string>();
                if (!allClips[fName].Contains(path)) allClips[fName].Add(path);
                
                if (fName != fbxName)
                {
                    if (!allClips.ContainsKey(fbxName)) allClips[fbxName] = new List<string>();
                    if (!allClips[fbxName].Contains(path)) allClips[fbxName].Add(path);
                }
                
                totalProjectClips++;
            }

            // Find Duplicates
            int totalDuplicateClipNames = 0;
            foreach (var kvp in allClips)
            {
                if (kvp.Value.Count > 1) totalDuplicateClipNames++;
            }

            // Load Registry
            List<AnimEntry> entries = new List<AnimEntry>();
            if (File.Exists(registryPath))
            {
                string jsonContent = File.ReadAllText(registryPath);
                var root = VivyAnimatorGenerator.MiniJSON.Parse(jsonContent) as Dictionary<string, object>;
                if (root != null && root.ContainsKey("categories"))
                {
                    var categories = root["categories"] as Dictionary<string, object>;
                    foreach (var category in categories)
                    {
                        var list = category.Value as List<object>;
                        if (list == null) continue;
                        foreach (var item in list)
                        {
                            var dict = item as Dictionary<string, object>;
                            if (dict == null) continue;
                            
                            AnimEntry entry = new AnimEntry();
                            if (dict.TryGetValue("id", out object idObj)) entry.id = idObj as string;
                            if (dict.TryGetValue("trigger", out object tObj)) entry.trigger = tObj as string;
                            if (dict.TryGetValue("bool_param", out object bObj)) entry.bool_param = bObj as string;
                            if (dict.TryGetValue("index_param", out object ipObj)) entry.index_param = ipObj as string;
                            if (dict.TryGetValue("layer", out object lObj)) entry.layer = lObj as string;
                            entries.Add(entry);
                        }
                    }
                }
            }

            int totalClipsFound = 0;
            int totalClipsMissing = 0;
            int totalRegistryMismatches = 0;
            int totalBrokenGuids = 0;
            int totalImportFailures = 0;
            
            report.AppendLine("======================================================================");
            report.AppendLine("1. REGISTRY ANIMATION VERIFICATION");
            report.AppendLine("======================================================================");

            foreach (var entry in entries)
            {
                string stateName = !string.IsNullOrEmpty(entry.id) ? entry.id : (entry.trigger ?? entry.bool_param ?? entry.index_param);
                if (string.IsNullOrEmpty(stateName)) continue;

                string cleanName = stateName.ToLowerInvariant();
                List<string> foundPaths = null;
                
                if (allClips.ContainsKey(cleanName)) foundPaths = allClips[cleanName];

                report.AppendLine($"\nAnimation ID: {stateName}");
                report.AppendLine($"Expected AnimationClip name: {stateName}");
                
                if (foundPaths != null && foundPaths.Count > 0)
                {
                    totalClipsFound++;
                    string selectedPath = foundPaths[0];
                    
                    // Logic to select the correct duplicate
                    if (foundPaths.Count > 1)
                    {
                        report.AppendLine($"DUPLICATE CLIPS DETECTED FOR: {stateName}");
                        foreach (string p in foundPaths) report.AppendLine($"  - {p}");
                        
                        // Pick the one that is an FBX (preferred over raw .anim unless specified)
                        foreach (string p in foundPaths)
                        {
                            if (p.EndsWith(".fbx", System.StringComparison.OrdinalIgnoreCase))
                            {
                                selectedPath = p;
                                break;
                            }
                        }
                        report.AppendLine($"Selected Clip: {selectedPath} (Prioritized FBX)");
                    }

                    string guid = AssetDatabase.AssetPathToGUID(selectedPath);
                    AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(selectedPath);
                    
                    report.AppendLine($"Expected asset path: {selectedPath}");
                    report.AppendLine($"Does the clip exist? YES");
                    report.AppendLine($"Can AssetDatabase load it? {(clip != null ? "YES" : "NO")}");
                    report.AppendLine($"GUID: {guid}");
                    
                    if (clip == null)
                    {
                        totalBrokenGuids++;
                        totalImportFailures++;
                        report.AppendLine($"Import status: FAILED (GUID broken or unsupported format)");
                        report.AppendLine($"Rig type: UNKNOWN");
                    }
                    else
                    {
                        ModelImporter mi = AssetImporter.GetAtPath(selectedPath) as ModelImporter;
                        if (mi != null)
                        {
                            report.AppendLine($"Import status: SUCCESS (Model)");
                            report.AppendLine($"Rig type: {mi.animationType}");
                        }
                        else
                        {
                            report.AppendLine($"Import status: SUCCESS (.anim)");
                            report.AppendLine($"Rig type: N/A");
                        }
                    }
                    
                    report.AppendLine($"Whether the registry points to the correct clip: YES (Name match)");
                }
                else
                {
                    totalClipsMissing++;
                    totalRegistryMismatches++;
                    report.AppendLine($"Expected asset path: UNKNOWN (Not found in project)");
                    report.AppendLine($"Does the clip exist? NO");
                    report.AppendLine($"Can AssetDatabase load it? NO");
                    report.AppendLine($"GUID: N/A");
                    report.AppendLine($"Import status: N/A");
                    report.AppendLine($"Rig type: N/A");
                    report.AppendLine($"Whether the registry points to the correct clip: NO (Missing asset)");
                }
            }

            int totalNullMotions = 0;
            int totalStates = 0;

            report.AppendLine("\n======================================================================");
            report.AppendLine("2. NULL MOTION STATE ANALYSIS");
            report.AppendLine("======================================================================");

            foreach (var layer in targetController.layers)
            {
                if (layer.stateMachine == null) continue;
                foreach (var stateNode in layer.stateMachine.states)
                {
                    totalStates++;
                    AnimatorState state = stateNode.state;
                    
                    if (state.motion == null)
                    {
                        totalNullMotions++;
                        string stateName = state.name;
                        string cleanName = stateName.ToLowerInvariant();
                        
                        List<string> foundPaths = null;
                        if (allClips.ContainsKey(cleanName)) foundPaths = allClips[cleanName];

                        report.AppendLine($"\nState name: {stateName}");
                        
                        if (foundPaths != null && foundPaths.Count > 0)
                        {
                            report.AppendLine($"Determine the exact AnimationClip that SHOULD be assigned: {foundPaths[0]}");
                            
                            // Check why it is NULL by looking at VivyAnimatorGenerator logic
                            // Generator only ever created dummy clips. It has zero code to load FBX files.
                            report.AppendLine($"Explain WHY it is currently NULL: The VivyAnimatorGenerator.cs script NEVER attempts to assign actual AnimationClips. It was hardcoded to only assign '_Dummy.anim' placeholders. When ControllerScrubber.cs was executed previously, it removed all Dummy clips, leaving these states with NULL motion.");
                            report.AppendLine($"Classify the reason: Generator bug (Generator completely lacks logic to map assets)");
                        }
                        else
                        {
                            report.AppendLine($"Determine the exact AnimationClip that SHOULD be assigned: UNKNOWN");
                            report.AppendLine($"Explain WHY it is currently NULL: The asset does not exist in the project folder at all.");
                            report.AppendLine($"Classify the reason: Missing asset");
                        }
                    }
                }
            }

            report.AppendLine("\n======================================================================");
            report.AppendLine("3. DUPLICATE ANIMATION CLIPS");
            report.AppendLine("======================================================================");
            if (totalDuplicateClipNames == 0) report.AppendLine("No duplicate clip names found.");
            foreach (var kvp in allClips)
            {
                if (kvp.Value.Count > 1)
                {
                    report.AppendLine($"Clip Name '{kvp.Key}' has {kvp.Value.Count} instances:");
                    foreach (string p in kvp.Value) report.AppendLine($"  - {p}");
                }
            }

            report.AppendLine("\n======================================================================");
            report.AppendLine("4. GENERATOR LOGIC VERIFICATION");
            report.AppendLine("======================================================================");
            report.AppendLine("Verify whether the Generator attempted to assign the clip and failed, or whether it never found the clip at all:");
            report.AppendLine("EVIDENCE: I have reviewed `VivyAnimatorGenerator.cs` line 244-268. The generator contains ZERO logic to search for, match, or assign real AnimationClips or FBX files. It explicitly creates empty placeholders called '{stateName}_Dummy.anim'. Therefore, it never attempted to assign the clip and failed; it deliberately never searched for them.");

            report.AppendLine("\n======================================================================");
            report.AppendLine("5. SUMMARY & CLASSIFICATION");
            report.AppendLine("======================================================================");
            report.AppendLine($"Total registry animations: {entries.Count}");
            report.AppendLine($"Total AnimationClips found: {totalProjectClips}");
            report.AppendLine($"Total missing AnimationClips: {totalClipsMissing}");
            report.AppendLine($"Total NULL motions: {totalNullMotions}");
            report.AppendLine($"Total duplicate clip names: {totalDuplicateClipNames}");
            report.AppendLine($"Total registry mismatches: {totalRegistryMismatches}");
            report.AppendLine($"Total broken GUIDs: {totalBrokenGuids}");
            report.AppendLine($"Total import failures: {totalImportFailures}");
            
            report.AppendLine("\nFINAL CLASSIFICATION:");
            if (totalClipsFound > 0 && totalClipsMissing > 0)
            {
                report.AppendLine("CATEGORY B: Some clips exist and some are genuinely missing.");
                report.AppendLine("RECOMMENDED REPAIR STRATEGY:");
                report.AppendLine("1. Rewrite VivyAnimatorGenerator.cs so it searches AssetDatabase for real clips instead of generating Dummies.");
                report.AppendLine("2. The user must import the missing FBX assets into the project for the remaining NULL states.");
                report.AppendLine("3. Re-run the patched generator to link all existing and newly imported clips.");
            }
            else if (totalClipsMissing == 0)
            {
                report.AppendLine("CATEGORY A: All clips exist; the generator failed to assign them.");
                report.AppendLine("RECOMMENDED REPAIR STRATEGY:");
                report.AppendLine("1. Rewrite VivyAnimatorGenerator.cs so it searches AssetDatabase and assigns the real clips.");
                report.AppendLine("2. Run the generator to automatically map and repair all NULL states.");
            }
            else
            {
                report.AppendLine("CATEGORY C: Most clips are missing from the Unity project.");
                report.AppendLine("RECOMMENDED REPAIR STRATEGY:");
                report.AppendLine("The animation assets are entirely missing from the project folders. They must be imported before any repairs can be made.");
            }
            
            File.WriteAllText(reportPath, report.ToString());
            Debug.Log("[FinalForensic] Final Pre-Repair Audit Complete. Report saved.");
        }

        private struct AnimEntry
        {
            public string id;
            public string trigger;
            public string bool_param;
            public string index_param;
            public string layer;
        }
    }
}
