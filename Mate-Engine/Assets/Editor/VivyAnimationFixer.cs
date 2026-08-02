using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.Collections.Generic;

/// <summary>
/// Corrected Phase 2 Fixer: 
/// Overrides the flawed UMotion clip assignments from the ResolutionDatabase 
/// and maps distinct, valid MATE ENGINE animations to avoid the A-Pose/T-Pose bug.
/// </summary>
public class VivyAnimationFixer : EditorWindow
{
    // Map each Idle state to a DISTINCT, valid humanoid animation clip from the verified ME_02 folder
    private static Dictionary<string, string> idleMappings = new Dictionary<string, string>
    {
        { "Idle0", "Assets/MATE ENGINE - Animations/PET_IDLE/ME_02/HUSBANDO/HUS_IDLE01.anim" },
        { "Idle1", "Assets/MATE ENGINE - Animations/PET_IDLE/ME_02/PET_IDLE_16.anim" },
        { "IdleHappy", "Assets/MATE ENGINE - Animations/PET_IDLE/ME_02/PET_IDLE_17.anim" },
        { "IdleCheer", "Assets/MATE ENGINE - Animations/PET_IDLE/ME_02/PET_IDLE_19.anim" },
        { "IdleSad", "Assets/MATE ENGINE - Animations/PET_IDLE/ME_02/PET_IDLE_20.anim" },
        { "IdleAngry", "Assets/MATE ENGINE - Animations/PET_IDLE/ME_02/PET_IDLE_21.anim" },
        { "IdleSurprise", "Assets/MATE ENGINE - Animations/PET_IDLE/ME_02/PET_IDLE_22.anim" }
    };

    [MenuItem("Vivy / Fix Animations (Corrected Idle Category)")]
    public static void FixCorrectedIdleCategory()
    {
        string controllerPath = "Assets/MATE ENGINE - Animations/AvatarAnimatorController.controller";
        AnimatorController controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);

        if (controller == null)
        {
            Debug.LogError($"[VivyAnimationFixer] Could not find AnimatorController at {controllerPath}");
            return;
        }

        AnimatorStateMachine rootStateMachine = controller.layers[0].stateMachine;
        int successCount = 0;

        foreach (var kvp in idleMappings)
        {
            string animId = kvp.Key;
            string clipPath = kvp.Value;

            AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
            if (clip == null)
            {
                Debug.LogWarning($"[VivyAnimationFixer] Could not load AnimationClip at {clipPath}");
                continue;
            }

            // 1. Ensure Trigger
            bool hasParam = false;
            foreach (var param in controller.parameters)
            {
                if (param.name == animId && param.type == AnimatorControllerParameterType.Trigger)
                {
                    hasParam = true;
                    break;
                }
            }
            if (!hasParam) controller.AddParameter(animId, AnimatorControllerParameterType.Trigger);

            // 2. Ensure State
            AnimatorState targetState = null;
            foreach (var childState in rootStateMachine.states)
            {
                if (childState.state.name == animId)
                {
                    targetState = childState.state;
                    break;
                }
            }
            if (targetState == null) targetState = rootStateMachine.AddState(animId);

            // 3. Assign the valid distinct clip
            targetState.motion = clip;

            // 4. Ensure AnyState Transition
            bool hasTransition = false;
            foreach (var transition in rootStateMachine.anyStateTransitions)
            {
                if (transition.destinationState == targetState)
                {
                    bool conditionExists = false;
                    foreach (var cond in transition.conditions)
                    {
                        if (cond.parameter == animId) conditionExists = true;
                    }
                    if (!conditionExists) transition.AddCondition(AnimatorConditionMode.If, 0, animId);
                    hasTransition = true;
                    break;
                }
            }

            if (!hasTransition)
            {
                var transition = rootStateMachine.AddAnyStateTransition(targetState);
                transition.AddCondition(AnimatorConditionMode.If, 0, animId);
                transition.hasExitTime = false;
                transition.duration = 0.25f; 
                transition.canTransitionToSelf = false; 
            }
            
            Debug.Log($"[VivyAnimationFixer] Wired {animId} to {clip.name} successfully.");
            successCount++;
        }

        EditorUtility.SetDirty(controller);
        AssetDatabase.SaveAssets();
        
        Debug.Log("=========================================================================");
        Debug.Log($"[VivyAnimationFixer] FIX APPLIED! Successfully assigned {successCount} distinct animations.");
        Debug.Log("=========================================================================");
    }
}
