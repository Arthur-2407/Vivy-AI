#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

[InitializeOnLoad]
public static class AutoPlay
{
    static AutoPlay()
    {
        Debug.Log($"[AutoPlay] Static constructor. isPlaying={EditorApplication.isPlaying}, activeScene={SceneManager.GetActiveScene().name}");
        
        // Monitor avatar continuously in Play Mode
        EditorApplication.update += MonitorAvatar;
        
        EditorApplication.delayCall += () =>
        {
            if (System.Environment.CommandLine.Contains("-autoplay") && !EditorApplication.isPlaying && !EditorApplication.isPaused)
            {
                Debug.Log("[AutoPlay] Requesting Play Mode now (-autoplay argument detected in command line)!");
                EditorApplication.isPlaying = true;
            }
        };
    }

    private static void MonitorAvatar()
    {
        if (!EditorApplication.isPlaying) return;

        var loader = Object.FindFirstObjectByType<VRMLoader>(FindObjectsInactive.Include);
        if (loader != null)
        {
            // Inject components into default model if present
            if (loader.mainModel != null && loader.mainModel.activeInHierarchy)
            {
                EnsureVivyComponents(loader.mainModel);
            }
            // Inject components into custom loaded model if present
            var customModel = loader.GetCurrentModel();
            if (customModel != null && customModel.activeInHierarchy)
            {
                EnsureVivyComponents(customModel);
            }
        }
    }

    private static void EnsureVivyComponents(GameObject go)
    {
        // 1. VivyEmotionMapper
        if (go.GetComponent<VivyEmotionMapper>() == null)
        {
            Debug.Log($"[AutoPlay] Dynamically adding VivyEmotionMapper to '{go.name}'");
            go.AddComponent<VivyEmotionMapper>();
        }
        // 2. VivyLipSync
        if (go.GetComponent<VivyLipSync>() == null)
        {
            Debug.Log($"[AutoPlay] Dynamically adding VivyLipSync to '{go.name}'");
            go.AddComponent<VivyLipSync>();
        }
        // 3. VivyWebSocketClient
        if (go.GetComponent<VivyWebSocketClient>() == null)
        {
            Debug.Log($"[AutoPlay] Dynamically adding VivyWebSocketClient to '{go.name}'");
            go.AddComponent<VivyWebSocketClient>();
        }
        // 3.5 VivyAnimationResolver
        if (go.GetComponent<VivyAnimationResolver>() == null)
        {
            Debug.Log($"[AutoPlay] Dynamically adding VivyAnimationResolver to '{go.name}'");
            go.AddComponent<VivyAnimationResolver>();
        }
        // 4. VivyAvatarStreamer
        if (go.GetComponent<VivyAvatarStreamer>() == null)
        {
            Debug.Log($"[AutoPlay] Dynamically adding VivyAvatarStreamer to '{go.name}'");
            go.AddComponent<VivyAvatarStreamer>();
        }
    }
}
#endif
