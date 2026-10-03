"""
Serviço de pesquisa de tendências via Reddit.
Extrai histórias de subreddits populares para usar como fonte de conteúdo.
"""
import os
import re
import json
import datetime
from typing import List, Dict, Optional
from pathlib import Path

import praw
from loguru import logger

from config import config


class RedditService:
    """Cliente Reddit para pesquisa de tendências e histórias."""
    
    # Subreddits favoritos para cada nicho
    SUBREDDITS = {
        "true_crime_brasileiro": ["r/brasil", "r/desabafos", "r/Telegrafos"],
        "true_crime_geral": [
            "r/TrueCrime", "r/UnresolvedMysteries", "r/LetsNotMeet",
            "r/TrueScaryStories", "r/nosleep", "r/creepyencounters"
        ],
        "mistorios": [
            "r/Mysterious", "r/UnresolvedMysteries", "r/Lost_Films",
            "r/RedditLegendarium"
        ],
        "default": ["r/TrueCrime", "r/UnresolvedMysteries", "r/brasil"]
    }
    
    def __init__(self, client_id: str = None, client_secret: str = None, user_agent: str = None):
        self.client_id = client_id or config.REDDIT_CLIENT_ID
        self.client_secret = client_secret or config.REDDIT_CLIENT_SECRET
        self.user_agent = user_agent or config.REDDIT_USER_AGENT
        self._reddit = None
    
    def _get_reddit(self):
        """Inicializa cliente Reddit."""
        if self._reddit is not None:
            return self._reddit
        
        if not self.client_id or not self.client_secret:
            logger.warning("Reddit credentials não configuradas - usando modo demo")
            return None
        
        try:
            self._reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent
            )
            # Testa conexão
            self._reddit.user.me()
            logger.info("Reddit conectado com sucesso")
            return self._reddit
        except Exception as e:
            logger.error(f"Erro ao conectar no Reddit: {e}")
            return None
    
    def get_trending_topics(self, niche: str = None, limit: int = 20) -> List[Dict]:
        """
        Busca posts em alta nos subreddits do nicho.
        
        Returns:
            Lista de dicts com {title, url, score, num_comments, subreddit, created_utc}
        """
        reddit = self._get_reddit()
        niche = niche or config.NICHO
        subreddits = self.SUBREDDITS.get(niche, self.SUBREDDITS["default"])
        
        posts = []
        
        if reddit is None:
            logger.warning("Reddit não disponível - retornando demos")
            return self._get_demo_topics()
        
        for subreddit_name in subreddits:
            try:
                subreddit = reddit.subreddit(subreddit_name)
                
                # Hot posts (popular agora)
                for post in subreddit.hot(limit=limit // len(subreddits)):
                    if self._is_suitable_topic(post.title, post.selftext or ""):
                        posts.append({
                            "title": post.title,
                            "url": f"https://reddit.com{post.permalink}",
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "subreddit": subreddit_name,
                            "created_utc": datetime.datetime.fromtimestamp(
                                post.created_utc, tz=datetime.timezone.utc
                            ).isoformat(),
                            "selftext": post.selftext[:500] if post.selftext else "",
                            " flair": post.link_flair_text or ""
                        })
                
                # Top posts da semana
                for post in subreddit.top("week", limit=limit // len(subreddits)):
                    if self._is_suitable_topic(post.title, post.selftext or ""):
                        posts.append({
                            "title": post.title,
                            "url": f"https://reddit.com{post.permalink}",
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "subreddit": subreddit_name,
                            "created_utc": datetime.datetime.fromtimestamp(
                                post.created_utc, tz=datetime.timezone.utc
                            ).isoformat(),
                            "selftext": post.selftext[:500] if post.selftext else "",
                            "flair": post.link_flair_text or ""
                        })
                        
            except Exception as e:
                logger.warning(f"Erro ao buscar r/{subreddit_name}: {e}")
        
        # Remove duplicatas por título
        seen = set()
        unique_posts = []
        for p in posts:
            if p["title"] not in seen:
                seen.add(p["title"])
                unique_posts.append(p)
        
        # Ordena por score
        unique_posts.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(f"Encontrados {len(unique_posts)} posts únicos em alta")
        return unique_posts[:limit]
    
    def get_post_details(self, url: str) -> Optional[Dict]:
        """Busca detalhes completos de um post específico."""
        reddit = self._get_reddit()
        if reddit is None:
            return None
        
        try:
            # Extrai ID do post da URL
            match = re.search(r'/comments/([a-zA-Z0-9]+)', url)
            if not match:
                return None
            
            submission = reddit.submission(id=match.group(1))
            
            # Asegura que comments estão carregados
            submission.comments.replace_more(limit=0)
            
            # Extrai comentários principais
            top_comments = []
            for comment in submission.comments[:5]:
                if len(comment.body) > 100:
                    top_comments.append({
                        "author": str(comment.author) if comment.author else "[deleted]",
                        "body": comment.body[:300],
                        "score": comment.score
                    })
            
            return {
                "title": submission.title,
                "selftext": submission.selftext,
                "url": f"https://reddit.com{submission.permalink}",
                "score": submission.score,
                "num_comments": submission.num_comments,
                "subreddit": str(submission.subreddit),
                "created_utc": datetime.datetime.fromtimestamp(
                    submission.created_utc, tz=datetime.timezone.utc
                ).isoformat(),
                "top_comments": top_comments,
                "media": self._extract_media(submission)
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar post {url}: {e}")
            return None
    
    def _is_suitable_topic(self, title: str, body: str = "") -> bool:
        """Filtra títulos que são adequados para o canal."""
        text = (title + " " + body).lower()
        
        # Deve ter keywords relevantes
        keywords = [
            "case", "crime", "murder", "mystery", "disappeared",
            "killed", "found", "strange", "vanished", "death",
            "investigation", "evidence", "witness", "suspect",
            "caso", "crime", "desaparecido", "morte", "mistério",
            "assassinato", "investigação", "suspeito", "prova"
        ]
        
        has_keyword = any(k in text for k in keywords)
        
        # Deve ter score razoável
        # Ignora posts curtos demais
        is_substantial = len(body) > 200 if body else len(title) > 30
        
        # Não é trabalho de spam
        is_not_spam = not any(s in text for s in [
            "http", "www", ".com", "subscribe", "instagram",
            "twitter", "youtube", "patreon", "buy", "sale"
        ][:8])  # check apenas primeiros
        
        return has_keyword and is_substantial
    
    def _extract_media(self, submission) -> Optional[Dict]:
        """Extrai informações de mídia do post."""
        media = {}
        
        if hasattr(submission, "url") and submission.url:
            media["url"] = submission.url
        
        if hasattr(submission, "is_video") and submission.is_video:
            media["type"] = "video"
        elif submission.url and any(
            submission.url.endswith(ext) for ext in [".jpg", ".png", ".gif", ".jpeg"]
        ):
            media["type"] = "image"
            media["url"] = submission.url
        
        return media if media else None
    
    def _get_demo_topics(self) -> List[Dict]:
        """Retorna topics demo quando Reddit não está configurado."""
        return [
            {
                "title": "O Caso do Hospital que Ninguém Falava (São Paulo, 2019)",
                "url": "https://reddit.com/r/brasil/example1",
                "score": 15420,
                "num_comments": 847,
                "subreddit": "r/brasil",
                "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "selftext": "Em 2019, um hospital em São Paulo foi fechado após revelações de irregularidades. As testemunhasdesapareceram uma a uma. Este é o relato completo.",
                "flair": "Discussão"
            },
            {
                "title": "O Desaparecimento queIntriga a Polícia há 7 Anos",
                "url": "https://reddit.com/r/TrueCrime/example2",
                "score": 8930,
                "num_comments": 412,
                "subreddit": "r/TrueCrime",
                "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "selftext": "Um homem saiu de casa para comprar cigarro em uma noite de sexta-feira. Nunca mais foi visto. A família ainda espera respostas.",
                "flair": "Missing Person"
            }
        ]


if __name__ == "__main__":
    reddit = RedditService()
    topics = reddit.get_trending_topics(limit=10)
    print(f"Posts encontrados: {len(topics)}")
    for t in topics[:3]:
        print(f"  [{t['score']} pts] {t['title']}")
