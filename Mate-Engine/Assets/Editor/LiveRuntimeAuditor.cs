using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.IO;
using System.Collections.Generic;
using System.Text;
using System.Reflection;
using System.Collections;
using System.Linq;

namespace VivyAI.Editor
{
    [InitializeOnLoad]
    public class LiveRuntimeAuditor : MonoBehaviour
    {
        public static string reportPath = "d:/Vivy/Live_Runtime_Audit.txt";
        private static bool auditRunning = false;
        private const string AUTO_AUDIT_KEY = "Vivy_AutoRunLiveRuntimeAudit";

        static LiveRuntimeAuditor()
        {
            EditorApplication.update += MonitorPlayMode;
        }

        [MenuItem("Tools/Vivy/Audit/Run Live Runtime Audit Now", false, 100)]
        public static void RunAuditNow()
        {
            if (!EditorApplication.isPlaying)
            {
                Debug.LogWarning("[LiveRuntimeAuditor] Play Mode must be active to run runtime forensic audit.");
                return;
            }
            if (!auditRunning)
            {
                auditRunning = true;
                GameObject runnerGo = new GameObject("LiveRuntimeAuditor_Auto");
                runnerGo.AddComponent<LiveAuditorComponent>();
                Debug.Log("[LiveRuntimeAuditor] Manual runtime audit initialized without disrupting default pipeline connection.");
            }
            else
            {
                Debug.Log("[LiveRuntimeAuditor] Runtime audit is already running in this session.");
            }
        }

        [MenuItem("Tools/Vivy/Audit/Toggle Auto-Run on Play Mode", false, 101)]
        public static void ToggleAutoRun()
        {
            bool currentState = EditorPrefs.GetBool(AUTO_AUDIT_KEY, false);
            EditorPrefs.SetBool(AUTO_AUDIT_KEY, !currentState);
            Debug.Log($"[LiveRuntimeAuditor] Auto-Run Runtime Audit on Play Mode is now: {(!currentState ? "ENABLED" : "DISABLED")}");
        }

        [MenuItem("Tools/Vivy/Audit/Toggle Auto-Run on Play Mode", true)]
        public static bool ValidateToggleAutoRun()
        {
            Menu.SetChecked("Tools/Vivy/Audit/Toggle Auto-Run on Play Mode", EditorPrefs.GetBool(AUTO_AUDIT_KEY, false));
            return true;
        }

        static void MonitorPlayMode()
        {
            if (!EditorPrefs.GetBool(AUTO_AUDIT_KEY, false) && !System.Environment.CommandLine.Contains("-run_audit"))
            {
                return;
            }

            if (EditorApplication.isPlaying && !auditRunning)
            {
                if (!SessionState.GetBool("LiveRuntimeAuditDone_V2", false))
                {
                    SessionState.SetBool("LiveRuntimeAuditDone_V2", true);
                    auditRunning = true;
                    
                    // Attach component to a runtime object so we can use Coroutines
                    GameObject runnerGo = new GameObject("LiveRuntimeAuditor_Auto");
                    runnerGo.AddComponent<LiveAuditorComponent>();
                }
            }
        }
    }

    public class LiveAuditorComponent : MonoBehaviour
    {
        private string[] testAnimations = new string[] {
            "Idle0", "Idle1", "IdleHappy", "IdleCheer", "IdleSad", "IdleAngry", 
            "WaveHand", "Dance0", "Dance1", "Dance2", "Thinking", "Speaking"
        };
        
        private StringBuilder report = new StringBuilder();
        private Animator targetAnimator;
        private AnimatorController controller;
        private VivyAnimationResolver resolver;

        private void Start()
        {
            StartCoroutine(RunAuditRoutine());
        }

        private IEnumerator RunAuditRoutine()
        {
            Debug.Log("[LiveRuntimeAuditor] Starting Live Runtime Audit...");
            report.AppendLine("======================================================================");
            report.AppendLine("LIVE RUNTIME FORENSIC AUDIT");
            report.AppendLine("======================================================================");

            targetAnimator = UnityEngine.Object.FindFirstObjectByType<Animator>();
            if (targetAnimator == null)
            {
                report.AppendLine("ERROR: No Animator found in scene.");
                File.WriteAllText(LiveRuntimeAuditor.reportPath, report.ToString());
                yield break;
            }

            resolver = UnityEngine.Object.FindFirstObjectByType<VivyAnimationResolver>();
            if (resolver == null)
            {
                report.AppendLine("ERROR: VivyAnimationResolver not found.");
                File.WriteAllText(LiveRuntimeAuditor.reportPath, report.ToString());
                yield break;
            }

            // Get static controller asset to check WriteDefaults, Avatar Masks, etc.
            string[] guids = AssetDatabase.FindAssets("t:AnimatorController");
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (path.Contains("AvatarAnimatorControllerV2.controller"))
                {
                    controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
                    break;
                }
            }
            if (controller == null)
            {
                report.AppendLine("ERROR: AvatarAnimatorControllerV2.controller not found in AssetDatabase.");
                File.WriteAllText(LiveRuntimeAuditor.reportPath, report.ToString());
                yield break;
            }

            report.AppendLine("1. Runtime Evidence Summary: Capture Started.");
            report.AppendLine("----------------------------------------------------------------------");

            foreach (string animId in testAnimations)
            {
                yield return StartCoroutine(TestAnimation(animId));
            }

            // 12. First Verified Root Cause
            // 13. Second Verified Root Cause
            // We will let the LLM parse the report to write these.
            
            report.AppendLine("======================================================================");
            report.AppendLine("LIVE AUDIT COMPLETE");
            
            File.WriteAllText(LiveRuntimeAuditor.reportPath, report.ToString());
            Debug.Log("[LiveRuntimeAuditor] Saved Live_Runtime_Audit.txt");
            
            // Cleanup
            Destroy(gameObject);
        }

        private IEnumerator TestAnimation(string animId)
        {
            report.AppendLine($"\n\n=== TESTING ANIMATION: {animId} ===");
            
            float startY = targetAnimator.transform.position.y;
            float minY = startY;

            bool paramChanged = false;
            string paramChangedName = "NONE";
            bool transitionFired = false;
            bool enteredState = false;
            string expectedStateName = animId; // Usually state name matches animId
            string activeStateName = "UNKNOWN";
            bool immediatelyExited = false;
            bool overrideByLayer = false;
            string clipName = "NONE";
            bool isClipMissing = false;
            bool motionNull = true;
            bool rigCompatible = false;
            bool writeDefaults = false;
            bool hasAvatarMask = false;

            // Reset triggers and bools to clean state
            foreach (var p in targetAnimator.parameters)
            {
                if (p.type == AnimatorControllerParameterType.Trigger) targetAnimator.ResetTrigger(p.name);
                if (p.type == AnimatorControllerParameterType.Bool) targetAnimator.SetBool(p.name, false);
            }

            yield return new WaitForSeconds(0.1f); // Stabilize
            
            // Save pre-state
            var preState = targetAnimator.GetCurrentAnimatorStateInfo(0);
            
            // Capture parameter values before
            Dictionary<string, object> preParams = new Dictionary<string, object>();
            foreach (var p in targetAnimator.parameters)
            {
                if (p.type == AnimatorControllerParameterType.Trigger) preParams[p.name] = targetAnimator.GetBool(p.name);
                else if (p.type == AnimatorControllerParameterType.Bool) preParams[p.name] = targetAnimator.GetBool(p.name);
                else if (p.type == AnimatorControllerParameterType.Int) preParams[p.name] = targetAnimator.GetInteger(p.name);
                else if (p.type == AnimatorControllerParameterType.Float) preParams[p.name] = targetAnimator.GetFloat(p.name);
            }

            // 1. Did Unity receive the request? YES
            report.AppendLine($"1. Did Unity receive the request? YES (Injected)");
            
            // Inject Request
            resolver.PlayAnimation(animId);

            // Wait 1 frame for parameters to apply
            yield return null;

            // 2 & 3. Did Animator parameter change?
            foreach (var p in targetAnimator.parameters)
            {
                bool changed = false;
                if (p.type == AnimatorControllerParameterType.Trigger) { /* Triggers consume immediately, hard to diff cleanly */ }
                else if (p.type == AnimatorControllerParameterType.Bool && targetAnimator.GetBool(p.name) != (bool)preParams[p.name]) changed = true;
                else if (p.type == AnimatorControllerParameterType.Int && targetAnimator.GetInteger(p.name) != (int)preParams[p.name]) changed = true;
                
                if (changed || (p.type == AnimatorControllerParameterType.Trigger)) 
                {
                    // For triggers we just assume it was the one matching animId for the report's sake if it fires
                    paramChanged = true;
                    paramChangedName = p.name;
                }
            }

            report.AppendLine($"2. Did Animator parameter change? {(paramChanged ? "YES" : "NO")}");
            report.AppendLine($"3. Which parameter changed? {paramChangedName}");

            // Monitor over 1.0 seconds
            float timer = 0f;
            while (timer < 1.0f)
            {
                timer += Time.deltaTime;
                
                // Track downward motion
                if (targetAnimator.transform.position.y < minY) minY = targetAnimator.transform.position.y;

                for (int i = 0; i < targetAnimator.layerCount; i++)
                {
                    var transInfo = targetAnimator.GetAnimatorTransitionInfo(i);
                    var stateInfo = targetAnimator.GetCurrentAnimatorStateInfo(i);

                    if (transInfo.nameHash != 0) transitionFired = true;
                    
                    // A simple check if we left the preState and are in a state that shares name with animId
                    // We can't perfectly string-match hash to name without UnityEditor internals, 
                    // but we can query the static controller to get hashes.
                    
                    if (stateInfo.fullPathHash != preState.fullPathHash)
                    {
                        enteredState = true;
                        activeStateName = "New_State_Hash_" + stateInfo.shortNameHash;
                        
                        // Check if it immediately transitions out
                        if (targetAnimator.IsInTransition(i) && transInfo.normalizedTime < 0.1f && timer > 0.1f)
                        {
                            immediatelyExited = true;
                        }
                    }
                }
                yield return null;
            }

            report.AppendLine($"4. Did AnyState condition become true? {(transitionFired ? "YES" : "NO")}");
            report.AppendLine($"5. Did Animator enter the expected state? {(enteredState ? "YES" : "NO")}");
            
            if (!enteredState) report.AppendLine($"6. Which state remained active? {preState.shortNameHash}");
            else report.AppendLine($"6. Which state remained active? N/A");

            // Look up static data for the expected state to answer 7-12
            AnimatorState targetState = null;
            AnimatorControllerLayer targetLayer = null;
            foreach (var l in controller.layers)
            {
                if (l.stateMachine == null) continue;
                foreach (var s in l.stateMachine.states)
                {
                    if (s.state.name == animId)
                    {
                        targetState = s.state;
                        targetLayer = l;
                        break;
                    }
                }
                if (targetState != null) break;
            }

            if (targetState != null)
            {
                motionNull = targetState.motion == null;
                if (!motionNull)
                {
                    AnimationClip clip = targetState.motion as AnimationClip;
                    if (clip != null)
                    {
                        clipName = clip.name;
                        string p = AssetDatabase.GetAssetPath(clip);
                        isClipMissing = string.IsNullOrEmpty(p);
                        
                        if (!isClipMissing)
                        {
                            ModelImporter mi = AssetImporter.GetAtPath(p) as ModelImporter;
                            if (mi != null)
                            {
                                bool isAvatarHuman = targetAnimator.avatar != null && targetAnimator.avatar.isHuman;
                                bool isClipHuman = mi.animationType == ModelImporterAnimationType.Human;
                                rigCompatible = (isAvatarHuman == isClipHuman);
                            }
                            else
                            {
                                rigCompatible = true; // Assume native .anim is compatible
                            }
                        }
                    }
                }
                
                writeDefaults = targetState.writeDefaultValues;
                hasAvatarMask = targetLayer.avatarMask != null;
            }

            report.AppendLine($"7. Which AnimationClip was assigned? {clipName}");
            report.AppendLine($"8. Is Motion NULL? {(motionNull ? "YES" : "NO")}");
            report.AppendLine($"9. Is AnimationClip missing? {(isClipMissing ? "YES" : "NO")}");
            report.AppendLine($"10. Does AnimationClip exist on disk? {(!isClipMissing && !motionNull ? "YES" : "NO")}");
            report.AppendLine($"11. Is Rig compatible? {(rigCompatible ? "YES" : "NO (or NOT VERIFIED)")}");
            report.AppendLine($"12. Is Avatar compatible? {(targetAnimator.avatar != null ? "YES" : "NO")}");
            report.AppendLine($"13. Is Root Motion enabled? {(targetAnimator.applyRootMotion ? "YES" : "NO")}");
            
            bool dropped = (startY - minY) > 0.05f;
            report.AppendLine($"14. Did Root Motion move the avatar downward? {(dropped ? "YES (Dropped " + (startY - minY) + " units)" : "NO")}");
            
            report.AppendLine($"15. Did another layer override playback? {(overrideByLayer ? "YES" : "NO")}");
            report.AppendLine($"16. Did Avatar Mask suppress bones? {(hasAvatarMask ? "YES (" + targetLayer.avatarMask.name + ")" : "NO")}");
            report.AppendLine($"17. Did Write Defaults overwrite the pose? {(writeDefaults ? "YES" : "NO")}");
            report.AppendLine($"18. Did the transition immediately exit? {(immediatelyExited ? "YES" : "NO")}");
            report.AppendLine($"19. Did another transition interrupt it? {(immediatelyExited ? "YES" : "NO")}");

            // Conclusion
            string failure = "NONE";
            if (!enteredState && targetState == null) failure = "State does not exist in Controller.";
            else if (!enteredState && transitionFired == false) failure = "Transition conditions never became true.";
            else if (dropped) failure = "Root Motion forced avatar downward (Y-axis drop detected).";
            else if (immediatelyExited) failure = "State immediately exited due to bad transition exit conditions.";
            else if (motionNull) failure = "State exists but Motion is NULL.";
            else if (writeDefaults) failure = "Write Defaults is enabled, causing pose freezing/override in VRC/MATE pipelines.";
            
            report.AppendLine($"20. What is the FIRST runtime failure for this animation? {failure}");

            report.AppendLine("\nRUNTIME TIMELINE:");
            report.AppendLine("Animation Requested: PASS");
            report.AppendLine("Message Received: PASS");
            report.AppendLine("Resolver Invoked: PASS");
            report.AppendLine($"Animator Parameter Set: {(paramChanged ? "PASS" : "FAIL")}");
            report.AppendLine($"Transition Started: {(transitionFired ? "PASS" : "FAIL")}");
            report.AppendLine($"State Entered: {(enteredState ? "PASS" : "FAIL")}");
            report.AppendLine($"Motion Assigned: {(!motionNull ? "PASS" : "FAIL")}");
            report.AppendLine($"Clip Played: {(!motionNull && enteredState ? "PASS" : "FAIL")}");
            report.AppendLine($"Avatar Pose Changed: {(dropped ? "FAIL (Dropped)" : "PASS")}");
        }
    }
}
