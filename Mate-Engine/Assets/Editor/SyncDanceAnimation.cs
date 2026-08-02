using UnityEngine;
using UnityEditor;

public class SyncDanceAnimation
{
    [UnityEditor.Callbacks.DidReloadScripts]
    private static void OnScriptsReloaded()
    {
        DoSync();
    }

    [MenuItem("Vivy/Sync Dance0 Animation")]
    public static void DoSync()
    {
        string flagFile = "d:/Vivy/shared/interchange/dance_sync_done.txt";
        // if (System.IO.File.Exists(flagFile)) return; // Commented out for forced execution

        string fbxPath = "Assets/MATE ENGINE - Animations/AI_Expanded_Assets/Dancing Maraschino Step.fbx";
        string targetPath = "Assets/MATE ENGINE - Animations/PET_DANCING/ME_02/HUSBANDO/HUS_DANCE_01.anim";

        // Must load all assets inside the FBX to find the AnimationClip
        Object[] allAssets = AssetDatabase.LoadAllAssetsAtPath(fbxPath);
        AnimationClip fbxClip = null;
        foreach(var asset in allAssets)
        {
            if (asset is AnimationClip && !asset.name.StartsWith("__preview__"))
            {
                fbxClip = asset as AnimationClip;
                break;
            }
        }

        AnimationClip targetClip = AssetDatabase.LoadAssetAtPath<AnimationClip>(targetPath);

        if (fbxClip != null && targetClip != null)
        {
            EditorUtility.CopySerialized(fbxClip, targetClip);
            targetClip.name = System.IO.Path.GetFileNameWithoutExtension(targetPath);
            EditorUtility.SetDirty(targetClip);
            AssetDatabase.SaveAssets();
            Debug.Log("[SyncDanceAnimation] Successfully synchronized 'Dancing Maraschino Step.fbx' into 'HUS_DANCE_01.anim' (The REAL Dance0 asset) without breaking references! Curve count: " + AnimationUtility.GetCurveBindings(targetClip).Length);
            System.IO.File.WriteAllText(flagFile, "done");
        }
        else
        {
            Debug.LogError($"[SyncDanceAnimation] Failed. fbxClip found: {fbxClip != null}, targetClip found: {targetClip != null}");
        }
    }
}
