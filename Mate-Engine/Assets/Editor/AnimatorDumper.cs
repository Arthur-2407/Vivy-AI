using UnityEngine;
using UnityEditor;
using UnityEditor.Animations;
using System.IO;

public static class AnimatorDumper
{
    public static void Dump()
    {
        string[] guids = AssetDatabase.FindAssets("t:AnimatorController");
        foreach (var guid in guids)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (path.Contains("Vivy"))
            {
                var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
                if (controller != null)
                {
                    string output = $"Controller: {controller.name}\n";
                    for (int i = 0; i < controller.layers.Length; i++)
                    {
                        var layer = controller.layers[i];
                        output += $"\nLayer {i}: {layer.name} | Weight: {layer.defaultWeight} | Blending: {layer.blendingMode}\n";
                        foreach (var state in layer.stateMachine.states)
                        {
                            string motionName = state.state.motion != null ? state.state.motion.name : "NULL";
                            output += $"  - State: {state.state.name} | Motion: {motionName}\n";
                        }
                    }
                    File.WriteAllText("d:/Vivy/animator_dump.txt", output);
                    Debug.Log($"Dumped to d:/Vivy/animator_dump.txt for {controller.name}");
                }
            }
        }
    }
}
