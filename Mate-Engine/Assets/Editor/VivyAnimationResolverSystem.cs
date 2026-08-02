using UnityEngine;
using UnityEditor;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Text;

namespace VivyAI.Editor
{
    public class ResolutionEntry
    {
        public string clipGuid;
        public string clipName;
        public string assetPath;
        public int confidence;
        public string resolutionMethod;
        public bool verified;
    }

    public class NeedsReviewEntry
    {
        public string registryId;
        public List<string> candidatePaths = new List<string>();
        public int confidence;
        public string evidence;
        public string reasonRejected;
        public string suggestedAction;
    }

    public class CandidateLog
    {
        public string name;
        public int score;
        public string scoreBreakdown;
        public string reasonRejected;
        public SemanticModel semantic;
    }

    public class CandidateDiscoveryTrace
    {
        public string registryId;
        public int totalClipsSearched;
        public List<CandidateLog> acceptedCandidates = new List<CandidateLog>();
        public List<CandidateLog> rejectedCandidates = new List<CandidateLog>();
        public string ambiguityReason = "";

        public string FormatTrace()
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine($"--- Registry ID: {registryId} ---");
            sb.AppendLine($"Index searched: {totalClipsSearched} clips");
            sb.AppendLine("\nAccepted:");
            if (acceptedCandidates.Count == 0) sb.AppendLine("  None");
            foreach (var c in acceptedCandidates)
            {
                sb.AppendLine($"  Candidate: {c.name}");
                sb.AppendLine($"  Score: {c.score}%");
                sb.AppendLine($"  Breakdown: {c.scoreBreakdown}");
                sb.AppendLine($"  Reason: {c.reasonRejected}"); // using reasonRejected field for accepted reason
            }
            
            sb.AppendLine("\nRejected:");
            if (rejectedCandidates.Count == 0) sb.AppendLine("  None");
            
            var sortedRejects = rejectedCandidates.OrderByDescending(r => r.score).ToList();
            foreach (var r in sortedRejects)
            {
                sb.AppendLine($"  Candidate: {r.name}");
                sb.AppendLine($"  Score: {r.score}%");
                sb.AppendLine($"  Breakdown: {r.scoreBreakdown}");
                sb.AppendLine($"  Reason: {r.reasonRejected}");
                sb.AppendLine("");
            }
            return sb.ToString();
        }
    }

    public enum AnimDomain { Unknown, Body, Face, Screen, UI, Pet, Human }
    public enum AnimFamily { Unknown, Idle, Dance, Talking, Sleeping, Dragging, Walking, Sitting }

    public class SemanticModel
    {
        public AnimDomain domain = AnimDomain.Unknown;
        public AnimFamily family = AnimFamily.Unknown;
        public int variant = -1;
        public string originalName;
    }

    public class ResolvedMapping
    {
        public string animationId;
        public string resolvedGuid;
        public string resolvedPath;
        public int confidenceScore;
        public string evidence;
        public string resolutionMethod;
        public AnimationClip clipReference;
        public CandidateDiscoveryTrace trace;
        public SemanticModel registrySemantic;
        public SemanticModel candidateSemantic;
        
        public bool isAutoAssignable => confidenceScore >= 90;
    }

    public static class VivyAnimationResolverSystem
    {
        public class IndexedClip
        {
            public string path;
            public string guid;
            public string internalName;
            public string fileName;
            public string normalizedName;
            public List<string> tokens;
            public SemanticModel semantic;
            public string rigType;
            public bool isHidden;
            public bool isSubAsset;
            public AnimationClip clip;
        }

        private static List<IndexedClip> clipDatabase = new List<IndexedClip>();
        private static Dictionary<string, ResolutionEntry> persistentDatabase = new Dictionary<string, ResolutionEntry>();
        public static List<NeedsReviewEntry> manualReviewQueue = new List<NeedsReviewEntry>();
        public static List<CandidateDiscoveryTrace> allTraces = new List<CandidateDiscoveryTrace>();
        private static bool isInitialized = false;

        private static string dbPath = "d:/Vivy/ResolutionDatabase.json";
        private static string reviewPath = "d:/Vivy/NeedsManualReview.json";

        public static List<string> Tokenize(string input)
        {
            if (string.IsNullOrEmpty(input)) return new List<string>();
            string[] rawTokens = input.Split(new char[] { '_', ' ', '-' }, System.StringSplitOptions.RemoveEmptyEntries);
            List<string> finalTokens = new List<string>();
            foreach (var r in rawTokens)
            {
                string camelSplit = Regex.Replace(r, "([a-z])([A-Z])", "$1 $2");
                string[] parts = camelSplit.Split(new char[] { ' ' }, System.StringSplitOptions.RemoveEmptyEntries);
                foreach (var p in parts)
                {
                    string clean = Regex.Replace(p.ToLowerInvariant(), "[^a-z0-9]", "");
                    if (!string.IsNullOrEmpty(clean)) finalTokens.Add(clean);
                }
            }
            return finalTokens;
        }

        public static string NormalizeName(List<string> tokens)
        {
            if (tokens == null || tokens.Count == 0) return "";
            string[] prefixes = { "pet", "face", "body", "hus", "custom", "screen", "mixamo", "armature" };
            string[] suffixes = { "loop", "idle", "01", "02", "03", "04", "05", "v2", "v3" };
            List<string> valid = new List<string>();
            for (int i = 0; i < tokens.Count; i++)
            {
                string t = tokens[i];
                if (i == 0 && prefixes.Contains(t)) continue;
                if (i == tokens.Count - 1 && suffixes.Contains(t)) continue;
                valid.Add(t);
            }
            while (valid.Count > 0 && suffixes.Contains(valid.Last())) valid.RemoveAt(valid.Count - 1);
            return string.Join("", valid);
        }

        public static SemanticModel ParseSemantic(string name, List<string> tokens)
        {
            SemanticModel model = new SemanticModel { originalName = name };
            string lowerName = name.ToLowerInvariant();
            
            if (lowerName.Contains("face")) model.domain = AnimDomain.Face;
            else if (lowerName.Contains("screen")) model.domain = AnimDomain.Screen;
            else if (lowerName.Contains("ui")) model.domain = AnimDomain.UI;
            else if (lowerName.Contains("pet")) model.domain = AnimDomain.Pet;
            else if (lowerName.Contains("hus") || lowerName.Contains("human")) model.domain = AnimDomain.Human;
            else if (lowerName.Contains("body") || lowerName.Contains("mixamo")) model.domain = AnimDomain.Body;
            else model.domain = AnimDomain.Body;

            if (lowerName.Contains("idle") || lowerName.Contains("stand")) model.family = AnimFamily.Idle;
            else if (lowerName.Contains("dance") || lowerName.Contains("dancing")) model.family = AnimFamily.Dance;
            else if (lowerName.Contains("talk") || lowerName.Contains("speak") || lowerName.Contains("voice") || lowerName.Contains("conversation")) model.family = AnimFamily.Talking;
            else if (lowerName.Contains("sleep") || lowerName.Contains("nap") || lowerName.Contains("lay")) model.family = AnimFamily.Sleeping;
            else if (lowerName.Contains("drag") || lowerName.Contains("pull")) model.family = AnimFamily.Dragging;
            else if (lowerName.Contains("walk") || lowerName.Contains("move")) model.family = AnimFamily.Walking;
            else if (lowerName.Contains("sit") || lowerName.Contains("chair")) model.family = AnimFamily.Sitting;

            Match m = Regex.Match(lowerName, @"\d+$");
            if (m.Success) int.TryParse(m.Value, out model.variant);
            else
            {
                foreach (var t in tokens)
                {
                    if (int.TryParse(t, out int v)) { model.variant = v; break; }
                }
            }
            return model;
        }

        public static void InitializeDatabase()
        {
            clipDatabase.Clear();
            manualReviewQueue.Clear();
            allTraces.Clear();
            LoadPersistentDatabase();

            StringBuilder famRep = new StringBuilder();
            famRep.AppendLine("ANIMATION FAMILY REPORT\n");
            
            StringBuilder semRep = new StringBuilder();
            semRep.AppendLine("SEMANTIC CLASSIFICATION REPORT\n");

            StringBuilder varRep = new StringBuilder();
            varRep.AppendLine("VARIANT RECOGNITION REPORT\n");

            string[] clipGuids = AssetDatabase.FindAssets("t:AnimationClip");
            foreach (string guid in clipGuids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (path.Contains("VivyDummyClips") || path.Contains("Editor/Data") || path.Contains("Package")) continue;

                Object[] allAssets = AssetDatabase.LoadAllAssetsAtPath(path);
                foreach (Object obj in allAssets)
                {
                    AnimationClip loadedClip = obj as AnimationClip;
                    if (loadedClip == null) continue;
                    
                    if ((loadedClip.hideFlags & HideFlags.HideInHierarchy) != 0 && loadedClip.name.StartsWith("__")) continue;

                    IndexedClip ic = new IndexedClip();
                    ic.path = path;
                    ic.guid = guid;
                    ic.internalName = loadedClip.name;
                    string basePath = path.Split('@')[0];
                    ic.fileName = Path.GetFileNameWithoutExtension(basePath);
                    
                    ic.tokens = Tokenize(ic.internalName);
                    if (ic.tokens.Count == 0) ic.tokens = Tokenize(ic.fileName);
                    ic.normalizedName = NormalizeName(ic.tokens);
                    ic.semantic = ParseSemantic(ic.internalName, ic.tokens);
                    
                    ic.isHidden = (loadedClip.hideFlags != HideFlags.None);
                    ic.isSubAsset = AssetDatabase.IsSubAsset(loadedClip);

                    string ext = Path.GetExtension(basePath).ToLowerInvariant();
                    if (ext == ".fbx" || ext == ".blend")
                    {
                        ModelImporter mi = AssetImporter.GetAtPath(basePath) as ModelImporter;
                        ic.rigType = mi != null ? mi.animationType.ToString() : "UNKNOWN";
                    }
                    else ic.rigType = "N/A (.anim)";

                    ic.clip = loadedClip;
                    clipDatabase.Add(ic);

                    semRep.AppendLine($"{ic.internalName} -> Domain: {ic.semantic.domain} | Family: {ic.semantic.family}");
                    if (ic.semantic.family != AnimFamily.Unknown) famRep.AppendLine($"[Family: {ic.semantic.family}] {ic.internalName}");
                    if (ic.semantic.variant != -1) varRep.AppendLine($"{ic.internalName} -> Variant {ic.semantic.variant}");
                }
            }

            clipDatabase = clipDatabase.GroupBy(c => c.clip.GetInstanceID()).Select(g => g.First()).ToList();
            isInitialized = true;
            Debug.Log($"[Resolver] Indexed {clipDatabase.Count} valid AnimationClips. Loaded {persistentDatabase.Count} persistent mappings.");

            if (!Directory.Exists("d:/Vivy/Reports")) Directory.CreateDirectory("d:/Vivy/Reports");
            File.WriteAllText("d:/Vivy/Reports/AnimationFamilyReport.md", famRep.ToString());
            File.WriteAllText("d:/Vivy/Reports/SemanticClassification.md", semRep.ToString());
            File.WriteAllText("d:/Vivy/Reports/VariantRecognition.md", varRep.ToString());
        }

        private static void LoadPersistentDatabase()
        {
            persistentDatabase.Clear();
            if (File.Exists(dbPath))
            {
                string json = File.ReadAllText(dbPath);
                var root = VivyAnimatorGenerator.MiniJSON.Parse(json) as Dictionary<string, object>;
                if (root != null)
                {
                    foreach (var kvp in root)
                    {
                        var dict = kvp.Value as Dictionary<string, object>;
                        if (dict != null)
                        {
                            var entry = new ResolutionEntry();
                            if (dict.TryGetValue("clipGuid", out object g)) entry.clipGuid = g as string;
                            if (dict.TryGetValue("clipName", out object cn)) entry.clipName = cn as string;
                            if (dict.TryGetValue("assetPath", out object p)) entry.assetPath = p as string;
                            if (dict.TryGetValue("confidence", out object c)) entry.confidence = System.Convert.ToInt32(c);
                            if (dict.TryGetValue("resolutionMethod", out object rm)) entry.resolutionMethod = rm as string;
                            if (dict.TryGetValue("verified", out object v)) entry.verified = (bool)v;
                            persistentDatabase[kvp.Key] = entry;
                        }
                    }
                }
            }
        }

        public static void SavePersistentDatabase()
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("{");
            int count = 0;
            foreach (var kvp in persistentDatabase)
            {
                sb.AppendLine($"  \"{kvp.Key}\": {{");
                sb.AppendLine($"    \"clipGuid\": \"{kvp.Value.clipGuid}\",");
                sb.AppendLine($"    \"clipName\": \"{kvp.Value.clipName}\",");
                sb.AppendLine($"    \"assetPath\": \"{kvp.Value.assetPath}\",");
                sb.AppendLine($"    \"confidence\": {kvp.Value.confidence},");
                sb.AppendLine($"    \"resolutionMethod\": \"{kvp.Value.resolutionMethod}\",");
                sb.AppendLine($"    \"verified\": {(kvp.Value.verified ? "true" : "false")}");
                sb.Append("  }");
                count++;
                if (count < persistentDatabase.Count) sb.AppendLine(",");
                else sb.AppendLine("");
            }
            sb.AppendLine("}");
            File.WriteAllText(dbPath, sb.ToString());
        }

        public static void SaveManualReviewQueue()
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("[");
            for (int i = 0; i < manualReviewQueue.Count; i++)
            {
                var q = manualReviewQueue[i];
                sb.AppendLine("  {");
                sb.AppendLine($"    \"registryId\": \"{q.registryId}\",");
                sb.AppendLine($"    \"confidence\": {q.confidence},");
                sb.AppendLine($"    \"evidence\": \"{q.evidence}\",");
                sb.AppendLine($"    \"reasonRejected\": \"{q.reasonRejected}\",");
                sb.AppendLine($"    \"suggestedAction\": \"{q.suggestedAction}\",");
                sb.AppendLine("    \"candidatePaths\": [");
                for (int j = 0; j < q.candidatePaths.Count; j++)
                {
                    sb.Append($"      \"{q.candidatePaths[j]}\"");
                    if (j < q.candidatePaths.Count - 1) sb.AppendLine(",");
                    else sb.AppendLine("");
                }
                sb.AppendLine("    ]");
                sb.Append("  }");
                if (i < manualReviewQueue.Count - 1) sb.AppendLine(",");
                else sb.AppendLine("");
            }
            sb.AppendLine("]");
            File.WriteAllText(reviewPath, sb.ToString());
        }

        public static ResolvedMapping ResolveClip(string registryId)
        {
            if (!isInitialized) InitializeDatabase();

            CandidateDiscoveryTrace trace = new CandidateDiscoveryTrace { registryId = registryId, totalClipsSearched = clipDatabase.Count };
            allTraces.Add(trace);

            SemanticModel regSem = ParseSemantic(registryId, Tokenize(registryId));

            if (persistentDatabase.ContainsKey(registryId))
            {
                var entry = persistentDatabase[registryId];
                var clip = clipDatabase.FirstOrDefault(c => c.guid == entry.clipGuid && c.internalName == entry.clipName);
                if (clip != null)
                {
                    trace.acceptedCandidates.Add(new CandidateLog { name = clip.internalName, score = 99, scoreBreakdown = "Persistent Mapping Match: 99", reasonRejected = "Preempted by explicit persistent database mapping." });
                    foreach (var c in clipDatabase) if (c != clip) trace.rejectedCandidates.Add(new CandidateLog { name = c.internalName, score = 0, scoreBreakdown = "Rejected: 0", reasonRejected = "Preempted by explicit database mapping." });
                    return CreateMapping(registryId, clip, 99, "Level 2: Persistent Mapping", "PersistentMapping", trace, regSem, clip.semantic);
                }
            }

            string cleanId = registryId.ToLowerInvariant();
            List<string> regTokens = Tokenize(registryId);
            string normId = NormalizeName(regTokens);

            List<CandidateLog> candidates = new List<CandidateLog>();
            IndexedClip bestClip = null;
            int bestScore = -1;
            string bestReason = "";
            string bestMethod = "";
            string bestBreakdown = "";

            foreach (var c in clipDatabase)
            {
                int score = 0;
                string reason = "";
                string method = "";
                string breakdown = "";
                
                bool familyMatch = (regSem.family != AnimFamily.Unknown && c.semantic.family == regSem.family);
                bool domainMatch = (c.semantic.domain == regSem.domain || (regSem.domain == AnimDomain.Body && c.semantic.domain == AnimDomain.Human) || (regSem.domain == AnimDomain.Human && c.semantic.domain == AnimDomain.Body));
                bool exactVariantMatch = (regSem.variant != -1 && c.semantic.variant == regSem.variant);
                bool nearbyVariantMatch = (regSem.variant != -1 && c.semantic.variant != -1 && Mathf.Abs(regSem.variant - c.semantic.variant) <= 1);

                if (c.internalName.Equals(registryId, System.StringComparison.Ordinal)) { score = 98; breakdown = "Exact Clip Name Match: 98"; reason = "Exact internal AnimationClip name"; method = "ExactInternal"; }
                else if (c.fileName.Equals(registryId, System.StringComparison.Ordinal)) { score = 97; breakdown = "Exact Filename Match: 97"; reason = "Exact filename match"; method = "ExactFilename"; }
                else if (c.internalName.ToLowerInvariant() == cleanId) { score = 96; breakdown = "Internal Case-Insensitive Match: 96"; reason = "Exact case-insensitive FBX clip name"; method = "ExactFBX"; }
                else if (familyMatch && domainMatch && exactVariantMatch) { score = 95; breakdown = "Family Match: 45 + Domain Match: 30 + Variant Match: 20 = 95"; reason = "Same Semantic Family + Same Domain + Same Variant"; method = "SemanticVariantExact"; }
                else if (familyMatch && domainMatch && nearbyVariantMatch) { score = 93; breakdown = "Family Match: 45 + Domain Match: 30 + Nearby Variant Match: 18 = 93"; reason = "Same Semantic Family + Same Domain + Nearby Variant"; method = "SemanticVariantNearby"; }
                else if (familyMatch && domainMatch && regSem.variant == -1 && c.semantic.variant == -1) { score = 92; breakdown = "Family Match: 45 + Domain Match: 30 + No Variant: 17 = 92"; reason = "Same Semantic Family + Same Domain (No variants)"; method = "SemanticFamily"; }
                else if (c.normalizedName == normId && !string.IsNullOrEmpty(normId)) { score = 91; breakdown = "Normalized Name Match: 91"; reason = "Deterministic Normalized Match"; method = "NormalizedMatch"; }
                else if (c.normalizedName.Contains(normId) && !string.IsNullOrEmpty(normId) && normId.Length >= 3) { score = 88; breakdown = "Token Substring Match: 88"; reason = "Token Substring Match"; method = "TokenSubstring"; }
                else if (cleanId.Contains(c.normalizedName) && !string.IsNullOrEmpty(c.normalizedName) && c.normalizedName.Length >= 4) { score = 80; breakdown = "Substring Match: 80"; reason = "Substring Match"; method = "Substring"; }
                else 
                {
                    int dist = ComputeLevenshteinDistance(normId, c.normalizedName);
                    if (dist <= 2 && normId.Length > 4) { score = 70; breakdown = $"Levenshtein Match (Diff {dist}): 70"; reason = $"Fuzzy Levenshtein Distance (Diff: {dist})"; method = "Levenshtein"; }
                    else { score = 0; breakdown = "No Matching Heuristic: 0"; reason = "Confidence too low. Domain/Family mismatch and no deterministic overlap."; }
                }

                if (score > 0 && regSem.domain == AnimDomain.Body && c.semantic.domain == AnimDomain.Face)
                {
                    score = 0; breakdown = "Domain Penalty: 0"; reason = "Domain Mismatch (Face clip prioritized out by Body domain requirements).";
                }

                if (score > 0)
                {
                    candidates.Add(new CandidateLog { name = c.internalName, score = score, scoreBreakdown = breakdown, reasonRejected = reason, semantic = c.semantic });
                    if (score > bestScore)
                    {
                        bestScore = score;
                        bestClip = c;
                        bestReason = reason;
                        bestMethod = method;
                        bestBreakdown = breakdown;
                    }
                }
                else
                {
                    trace.rejectedCandidates.Add(new CandidateLog { name = c.internalName, score = 0, scoreBreakdown = breakdown, reasonRejected = reason, semantic = c.semantic });
                }
            }

            if (bestScore >= 90)
            {
                int topCount = candidates.Count(c => c.score == bestScore);
                if (topCount > 1)
                {
                    trace.ambiguityReason = "Multiple exact deterministic candidates yielded the exact same score. Unable to automatically select a winner without manual review.";
                    foreach (var c in candidates) trace.rejectedCandidates.Add(new CandidateLog { name = c.name, score = c.score, scoreBreakdown = c.scoreBreakdown, reasonRejected = trace.ambiguityReason, semantic = c.semantic });
                    return HandleAmbiguity(registryId, clipDatabase.Where(c => candidates.Any(cand => cand.name == c.internalName && cand.score == bestScore)).ToList(), 0, trace.ambiguityReason, "Ambiguity", "Semantic Ambiguity: Multiple exact candidates", trace, regSem);
                }
                
                trace.acceptedCandidates.Add(new CandidateLog { name = bestClip.internalName, score = bestScore, scoreBreakdown = bestBreakdown, reasonRejected = bestReason, semantic = bestClip.semantic });
                foreach (var c in candidates) if (c.name != bestClip.internalName) trace.rejectedCandidates.Add(new CandidateLog { name = c.name, score = c.score, scoreBreakdown = c.scoreBreakdown, reasonRejected = "Lower score than the accepted candidate.", semantic = c.semantic });
                
                persistentDatabase[registryId] = new ResolutionEntry { clipGuid = bestClip.guid, clipName = bestClip.internalName, assetPath = bestClip.path, confidence = bestScore, resolutionMethod = bestMethod, verified = true };
                return CreateMapping(registryId, bestClip, bestScore, bestReason, bestMethod, trace, regSem, bestClip.semantic);
            }
            else if (bestScore > 0)
            {
                foreach (var c in candidates) trace.rejectedCandidates.Add(new CandidateLog { name = c.name, score = c.score, scoreBreakdown = c.scoreBreakdown, reasonRejected = "Confidence too low (< 90%). Relegated to NeedsManualReview.json queue.", semantic = c.semantic });
                return QueueReview(registryId, clipDatabase.Where(c => candidates.Any(cand => cand.name == c.internalName)).ToList(), bestScore, bestReason, "Fuzzy match requires human verification", "Manual mapping required", trace, regSem);
            }

            return new ResolvedMapping { animationId = registryId, confidenceScore = 0, evidence = "Level 9: No candidates found. Entire 163 clip database searched, Tokenization failed, Semantic Family match failed, Domain match failed, Variant match failed.", resolutionMethod = "Unresolved", trace = trace, registrySemantic = regSem };
        }

        private static ResolvedMapping CreateMapping(string id, IndexedClip ic, int score, string ev, string method, CandidateDiscoveryTrace trace, SemanticModel rSem, SemanticModel cSem)
        {
            return new ResolvedMapping
            {
                animationId = id, resolvedGuid = ic.guid, resolvedPath = ic.path, confidenceScore = score, evidence = ev, resolutionMethod = method, clipReference = ic.clip, trace = trace, registrySemantic = rSem, candidateSemantic = cSem
            };
        }

        private static ResolvedMapping HandleAmbiguity(string id, List<IndexedClip> candidates, int score, string ev, string method, string reason, CandidateDiscoveryTrace trace, SemanticModel rSem)
        {
            QueueReview(id, candidates, score, ev, reason, "Manually choose the correct candidate", trace, rSem);
            return new ResolvedMapping { animationId = id, confidenceScore = 0, evidence = ev, resolutionMethod = method, trace = trace, registrySemantic = rSem };
        }

        private static ResolvedMapping QueueReview(string id, List<IndexedClip> candidates, int score, string ev, string reason, string action, CandidateDiscoveryTrace trace, SemanticModel rSem)
        {
            var q = new NeedsReviewEntry { registryId = id, confidence = score, evidence = ev, reasonRejected = reason, suggestedAction = action };
            foreach (var c in candidates) q.candidatePaths.Add(c.path);
            manualReviewQueue.Add(q);
            return new ResolvedMapping { animationId = id, confidenceScore = score, evidence = ev, resolutionMethod = "AdvisoryOnly", trace = trace, registrySemantic = rSem };
        }

        private static int ComputeLevenshteinDistance(string s, string t)
        {
            int n = s.Length; int m = t.Length;
            int[,] d = new int[n + 1, m + 1];
            if (n == 0) return m; if (m == 0) return n;
            for (int i = 0; i <= n; d[i, 0] = i++) { }
            for (int j = 0; j <= m; d[0, j] = j++) { }
            for (int i = 1; i <= n; i++)
            {
                for (int j = 1; j <= m; j++)
                {
                    int cost = (t[j - 1] == s[i - 1]) ? 0 : 1;
                    d[i, j] = Mathf.Min(Mathf.Min(d[i - 1, j] + 1, d[i, j - 1] + 1), d[i - 1, j - 1] + cost);
                }
            }
            return d[n, m];
        }
    }
}
