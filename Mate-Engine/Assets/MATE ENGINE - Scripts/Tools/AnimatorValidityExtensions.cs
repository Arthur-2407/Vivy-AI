using UnityEngine;

public static class AnimatorValidityExtensions
{
    public static bool IsValidAndPlaying(this Animator animator)
    {
        return animator != null &&
               animator.runtimeAnimatorController != null &&
               animator.enabled &&
               animator.gameObject.activeInHierarchy;
    }
}
