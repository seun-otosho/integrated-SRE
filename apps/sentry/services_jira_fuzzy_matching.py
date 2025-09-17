import logging
import re
from typing import Dict, List, Optional, Tuple
from django.db.models import Q
from difflib import SequenceMatcher
from django.utils import timezone as django_timezone

logger = logging.getLogger(__name__)


class SentryJiraFuzzyMatchingService:
    """Service for finding JIRA tickets that match Sentry issue titles using fuzzy matching"""
    
    def __init__(self):
        self.min_similarity = 0.7  # Minimum similarity threshold (70%)
        self.min_title_length = 10  # Minimum title length to consider
    
    def find_matching_jira_tickets(self, sentry_issue, similarity_threshold: float = None) -> List[Dict]:
        """Find JIRA tickets that might match a Sentry issue based on title similarity"""
        from apps.jira.models import JiraIssue
        
        threshold = similarity_threshold or self.min_similarity
        matches = []
        
        # Skip very short titles
        if len(sentry_issue.title) < self.min_title_length:
            return matches
        
        # Clean and normalize the Sentry issue title
        sentry_title_clean = self._clean_title(sentry_issue.title)
        sentry_keywords = self._extract_keywords(sentry_title_clean)
        
        # Get potential JIRA issues to compare against
        potential_jira_issues = self._get_potential_jira_matches(sentry_keywords)
        
        for jira_issue in potential_jira_issues:
            # Clean and normalize JIRA summary
            jira_summary_clean = self._clean_title(jira_issue.summary)
            
            # Calculate various similarity scores
            similarity_scores = self._calculate_similarity_scores(
                sentry_title_clean, jira_summary_clean
            )
            
            # Use the highest similarity score
            max_similarity = max(similarity_scores.values())
            
            if max_similarity >= threshold:
                matches.append({
                    'jira_issue': jira_issue,
                    'similarity_score': max_similarity,
                    'similarity_details': similarity_scores,
                    'sentry_title': sentry_issue.title,
                    'jira_summary': jira_issue.summary,
                    'match_type': self._determine_match_type(similarity_scores)
                })
        
        # Sort by similarity score (highest first)
        matches.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return matches
    
    def _clean_title(self, title: str) -> str:
        """Clean and normalize a title for comparison"""
        if not title:
            return ""
        
        # Convert to lowercase
        cleaned = title.lower()
        
        # Remove common prefixes/suffixes
        prefixes_to_remove = [
            r'^error:\s*',
            r'^exception:\s*',
            r'^warning:\s*',
            r'^bug:\s*',
            r'^\[.*?\]\s*',  # Remove [tags]
        ]
        
        for prefix in prefixes_to_remove:
            cleaned = re.sub(prefix, '', cleaned)
        
        # Remove special characters but keep spaces and alphanumeric
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        
        # Normalize whitespace
        cleaned = ' '.join(cleaned.split())
        
        return cleaned.strip()
    
    def _extract_keywords(self, title: str) -> List[str]:
        """Extract meaningful keywords from a title"""
        if not title:
            return []
        
        # Split into words
        words = title.split()
        
        # Filter out common stop words and very short words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does',
            'did', 'will', 'would', 'could', 'should', 'can', 'cannot', 'cant', 'this', 'that',
            'these', 'those', 'error', 'exception', 'warning', 'issue', 'problem', 'bug'
        }
        
        keywords = [
            word for word in words 
            if len(word) > 2 and word not in stop_words
        ]
        
        return keywords
    
    def _get_potential_jira_matches(self, keywords: List[str]) -> List:
        """Get JIRA issues that might be potential matches based on keywords"""
        from apps.jira.models import JiraIssue
        
        if not keywords:
            return JiraIssue.objects.none()
        
        # Build a query that looks for issues containing any of the keywords
        q_objects = Q()
        for keyword in keywords[:5]:  # Limit to first 5 keywords to avoid slow queries
            q_objects |= Q(summary__icontains=keyword)
        
        # Get potential matches, limited to reasonable number
        return JiraIssue.objects.filter(q_objects).distinct()[:100]
    
    def _calculate_similarity_scores(self, sentry_title: str, jira_summary: str) -> Dict[str, float]:
        """Calculate various similarity scores between two titles"""
        scores = {}
        
        # 1. Sequence matcher - overall similarity
        scores['sequence_similarity'] = SequenceMatcher(None, sentry_title, jira_summary).ratio()
        
        # 2. Word overlap similarity
        sentry_words = set(sentry_title.split())
        jira_words = set(jira_summary.split())
        
        if sentry_words and jira_words:
            intersection = sentry_words.intersection(jira_words)
            union = sentry_words.union(jira_words)
            scores['word_overlap'] = len(intersection) / len(union)
        else:
            scores['word_overlap'] = 0.0
        
        # 3. Keyword overlap similarity (weighted more heavily)
        sentry_keywords = set(self._extract_keywords(sentry_title))
        jira_keywords = set(self._extract_keywords(jira_summary))
        
        if sentry_keywords and jira_keywords:
            keyword_intersection = sentry_keywords.intersection(jira_keywords)
            keyword_union = sentry_keywords.union(jira_keywords)
            scores['keyword_overlap'] = len(keyword_intersection) / len(keyword_union)
        else:
            scores['keyword_overlap'] = 0.0
        
        # 4. Substring similarity (for exact phrase matches)
        scores['substring_similarity'] = self._calculate_substring_similarity(sentry_title, jira_summary)
        
        return scores
    
    def _calculate_substring_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity based on longest common substrings"""
        if not text1 or not text2:
            return 0.0
        
        # Find longest common substring
        max_length = 0
        for i in range(len(text1)):
            for j in range(len(text2)):
                length = 0
                while (i + length < len(text1) and 
                       j + length < len(text2) and 
                       text1[i + length] == text2[j + length]):
                    length += 1
                max_length = max(max_length, length)
        
        # Normalize by the length of the shorter string
        return max_length / min(len(text1), len(text2))
    
    def _determine_match_type(self, similarity_scores: Dict[str, float]) -> str:
        """Determine the type of match based on similarity scores"""
        if similarity_scores['keyword_overlap'] > 0.8:
            return 'high_keyword_match'
        elif similarity_scores['sequence_similarity'] > 0.8:
            return 'high_sequence_match'
        elif similarity_scores['word_overlap'] > 0.7:
            return 'high_word_overlap'
        elif similarity_scores['substring_similarity'] > 0.6:
            return 'good_substring_match'
        else:
            return 'moderate_match'
    
    def scan_and_suggest_matches(self, organization=None, limit: int = 50, 
                                similarity_threshold: float = None) -> Dict:
        """Scan Sentry issues and suggest JIRA ticket matches"""
        from apps.sentry.models import SentryIssue
        from apps.jira.models import SentryJiraLink
        
        threshold = similarity_threshold or self.min_similarity
        results = {
            'issues_scanned': 0,
            'potential_matches_found': 0,
            'high_confidence_matches': 0,
            'suggestions': [],
            'summary': {}
        }
        
        # Get Sentry issues that don't already have JIRA links
        linked_issue_ids = SentryJiraLink.objects.values_list('sentry_issue_id', flat=True)
        
        queryset = SentryIssue.objects.exclude(id__in=linked_issue_ids).select_related(
            'project', 'project__organization'
        )
        
        if organization:
            queryset = queryset.filter(project__organization=organization)
        
        # Order by most recent first
        queryset = queryset.order_by('-last_seen')[:limit]
        
        for sentry_issue in queryset:
            results['issues_scanned'] += 1
            
            matches = self.find_matching_jira_tickets(sentry_issue, threshold)
            
            if matches:
                results['potential_matches_found'] += 1
                
                # Count high confidence matches (>= 80% similarity)
                high_confidence = [m for m in matches if m['similarity_score'] >= 0.8]
                if high_confidence:
                    results['high_confidence_matches'] += 1
                
                suggestion = {
                    'sentry_issue': sentry_issue,
                    'matches': matches[:3],  # Top 3 matches
                    'best_match': matches[0] if matches else None,
                    'confidence': 'high' if high_confidence else 'medium'
                }
                
                results['suggestions'].append(suggestion)
        
        # Generate summary
        results['summary'] = {
            'scan_rate': f"{results['potential_matches_found']}/{results['issues_scanned']}",
            'match_rate_percent': round(
                (results['potential_matches_found'] / max(results['issues_scanned'], 1)) * 100, 1
            ),
            'high_confidence_rate': round(
                (results['high_confidence_matches'] / max(results['potential_matches_found'], 1)) * 100, 1
            )
        }
        
        return results
    
    def create_links_from_suggestions(self, suggestions: List[Dict], 
                                    auto_create_high_confidence: bool = False,
                                    min_confidence_score: float = 0.85) -> Dict:
        """Create JIRA links from fuzzy match suggestions"""
        from apps.jira.models import SentryJiraLink
        
        results = {
            'links_created': 0,
            'high_confidence_created': 0,
            'manual_review_needed': 0,
            'errors': []
        }
        
        for suggestion in suggestions:
            sentry_issue = suggestion['sentry_issue']
            best_match = suggestion['best_match']
            
            if not best_match:
                continue
            
            jira_issue = best_match['jira_issue']
            similarity_score = best_match['similarity_score']
            
            try:
                # Check if link already exists
                existing_link = SentryJiraLink.objects.filter(
                    sentry_issue=sentry_issue,
                    jira_issue=jira_issue
                ).first()
                
                if existing_link:
                    continue
                
                # Decide whether to auto-create or flag for manual review
                should_auto_create = (
                    auto_create_high_confidence and 
                    similarity_score >= min_confidence_score
                )
                
                if should_auto_create:
                    # Auto-create high confidence matches
                    link = SentryJiraLink.objects.create(
                        sentry_issue=sentry_issue,
                        jira_issue=jira_issue,
                        link_type='auto',
                        creation_notes=f"Auto-linked via fuzzy matching (similarity: {similarity_score:.2%})",
                        sync_sentry_to_jira=True,
                        sync_jira_to_sentry=True
                    )
                    
                    results['links_created'] += 1
                    results['high_confidence_created'] += 1
                    
                    logger.info(f"Auto-created fuzzy match link: {sentry_issue} -> {jira_issue}")
                else:
                    # Flag for manual review
                    results['manual_review_needed'] += 1
                
            except Exception as e:
                results['errors'].append(f"Error linking {sentry_issue} to {jira_issue}: {str(e)}")
        
        return results