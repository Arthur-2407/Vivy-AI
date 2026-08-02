using System;
using System.Collections.Generic;
using UnityEngine;
using Vivy.Logging;

namespace Vivy.Recovery
{
    /// <summary>
    /// Vivy Error Recovery System for Unity (v1.0.0).
    /// Per Rule 10 of the Master Hyperprompt.
    /// Provides component isolation, fallback animation triggers,
    /// and safe fallback execution.
    /// </summary>
    public static class VivyErrorRecovery
    {
        private static readonly Dictionary<string, Func<object>> _fallbacks = new Dictionary<string, Func<object>>();
        private static readonly Dictionary<string, int> _errorCounts = new Dictionary<string, int>();

        public static void RegisterFallback(string subsystem, Func<object> fallbackFunc)
        {
            _fallbacks[subsystem] = fallbackFunc;
            VivyLogger.Info("ErrorRecovery", $"Registered fallback strategy for subsystem '{subsystem}'");
        }

        public static T ExecuteSafe<T>(string subsystem, Func<T> action, T defaultValue = default)
        {
            try
            {
                T result = action();
                _errorCounts[subsystem] = 0;
                return result;
            }
            catch (Exception ex)
            {
                VivyLogger.Error("ErrorRecovery", $"Subsystem '{subsystem}' threw exception: {ex.Message}");
                if (!_errorCounts.ContainsKey(subsystem)) _errorCounts[subsystem] = 0;
                _errorCounts[subsystem]++;

                if (_fallbacks.TryGetValue(subsystem, out var fallback))
                {
                    try
                    {
                        VivyLogger.Warn("ErrorRecovery", $"Invoking fallback for subsystem '{subsystem}'");
                        return (T)fallback();
                    }
                    catch (Exception fallbackEx)
                    {
                        VivyLogger.Error("ErrorRecovery", $"Fallback failed for subsystem '{subsystem}': {fallbackEx.Message}");
                    }
                }

                return defaultValue;
            }
        }

        public static void ExecuteSafeAction(string subsystem, Action action)
        {
            ExecuteSafe<bool>(subsystem, () => { action(); return true; }, false);
        }
    }
}
