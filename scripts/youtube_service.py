"""
Serviço de integração com YouTube Data API v3 e YouTube Analytics API.
Responsável por upload, agendamento, gerenciamento de playlists e coleta de métricas.
"""
import os
import json
import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from loguru import logger

from config import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"


class YouTubeService:
    """Cliente YouTube API completo para o Canal Dark."""
    
    def __init__(self, api_key: str = None, credentials_path: str = None):
        self.api_key = api_key or config.YOUTUBE_API_KEY
        self.channel_id = config.YOUTUBE_CHANNEL_ID
        self.credentials_path = credentials_path
        self._youtube = None
        self._credentials = None
    
    def _get_authenticated_service(self):
        """Autentica via OAuth2 (para upload/agendamento)."""
        if self._youtube is not None:
            return self._youtube
        
        credentials = None
        token_path = Path(__file__).parent.parent / "dados" / "youtube_token.json"
        
        if token_path.exists():
            import pickle
            with open(token_path, "rb") as f:
                credentials = pickle.load(f)
        
        if credentials is None or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh()
                logger.info("Token OAuth2 refresh feito")
            else:
                logger.error("É necessário autenticar no YouTube. Execute youtube_auth.py primeiro.")
                return None
        
        self._youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        return self._youtube
    
    def upload_video(
        self,
        file_path: str,
        title: str,
        description: str,
        tags: List[str],
        category_id: str = "24",  # Entertainment
        privacy_status: str = "private",  # private, public, unlisted
        publish_at: Optional[datetime.datetime] = None,
        playlist_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Faz upload de um vídeo para o YouTube.
        
        Args:
            file_path: Caminho do arquivo de vídeo
            title: Título do vídeo
            description: Descrição do vídeo
            tags: Lista de tags
            category_id: ID da categoria YouTube
            privacy_status: 'private', 'public', ou 'unlisted'
            publish_at: Datetime para agendamento (None = publicar imediatamente)
            playlist_id: ID da playlist para adicionar o vídeo
        
        Returns:
            Dict com videoId e outros detalhes ou None em caso de erro
        """
        youtube = self._get_authenticated_service()
        if youtube is None:
            logger.error("YouTube API não disponível - verifique autenticação")
            return None
        
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
                "defaultLanguage": "pt-BR",
                "localizations": {"pt-BR": {"title": title, "description": description}}
            },
            "status": {
                "privacyStatus": privacy_status,
                "publishAt": publish_at.isoformat() + "Z" if publish_at else None,
                "selfDeclaredMadeForKids": False,
            },
            "recordingDetails": {
                "locationDescription": "Brasil",
                "recordingDate": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        }
        
        # Remove publishAt se não for agendamento
        if publish_at is None:
            del body["status"]["publishAt"]
        
        try:
            media = MediaFileUpload(
                file_path,
                chunksize=-1,
                resumable=True,
                mimetype="video/mp4"
            )
            
            request = youtube.videos().insert(
                part="snippet,status,recordingDetails",
                body=body,
                media_body=media
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Upload: {int(status.progress() * 100)}%")
            
            video_id = response.get("id")
            logger.info(f"Upload concluído: videoId={video_id}")
            
            # Adiciona à playlist se informada
            if playlist_id and video_id:
                self._add_to_playlist(video_id, playlist_id)
            
            return response
            
        except Exception as e:
            logger.error(f"Erro no upload: {e}")
            return None
    
    def _add_to_playlist(self, video_id: str, playlist_id: str) -> bool:
        """Adiciona vídeo a uma playlist."""
        youtube = self._get_authenticated_service()
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id}
                    }
                }
            ).execute()
            logger.info(f"Vídeo {video_id} adicionado à playlist {playlist_id}")
            return True
        except Exception as e:
            logger.warning(f"Não foi possível adicionar à playlist: {e}")
            return False
    
    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "public"
    ) -> Optional[str]:
        """Cria uma playlist e retorna o ID."""
        youtube = self._get_authenticated_service()
        if youtube is None:
            return None
        
        try:
            response = youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": title,
                        "description": description,
                        "defaultLanguage": "pt-BR"
                    },
                    "status": {"privacyStatus": privacy_status}
                }
            ).execute()
            playlist_id = response["id"]
            logger.info(f"Playlist criada: {title} (ID: {playlist_id})")
            return playlist_id
        except Exception as e:
            logger.error(f"Erro ao criar playlist: {e}")
            return None
    
    def get_channel_playlists(self) -> List[Dict]:
        """Lista playlists do canal."""
        youtube = self._get_authenticated_service()
        if youtube is None:
            return []
        
        try:
            response = youtube.playlists().list(
                part="snippet,contentDetails",
                channelId=self.channel_id,
                maxResults=50
            ).execute()
            return response.get("items", [])
        except Exception as e:
            logger.error(f"Erro ao listar playlists: {e}")
            return []
    
    def get_video_metrics(
        self,
        video_id: str = None,
        start_date: str = "2024-01-01",
        end_date: str = None
    ) -> Dict[str, Any]:
        """
        Coleta métricas de vídeos via YouTube Analytics API.
        
        Args:
            video_id: ID de vídeo específico (None = todo o canal)
            start_date: Data inicial (YYYY-MM-DD)
            end_date: Data final (YYYY-MM-DD, padrão = hoje)
        
        Returns:
            Dict com métricas
        """
        if end_date is None:
            end_date = datetime.date.today().isoformat()
        
        # Usa YouTube Data API (mais limitado mas não requer OAuth específico)
        youtube = build(API_SERVICE_NAME, API_VERSION, developerKey=self.api_key)
        
        if video_id:
            try:
                response = youtube.videos().list(
                    part="snippet,statistics,contentDetails",
                    id=video_id
                ).execute()
                
                if response["items"]:
                    item = response["items"][0]
                    return {
                        "video_id": video_id,
                        "title": item["snippet"]["title"],
                        "views": int(item["statistics"].get("viewCount", 0)),
                        "likes": int(item["statistics"].get("likeCount", 0)),
                        "comments": int(item["statistics"].get("commentCount", 0)),
                        "duration": item["contentDetails"]["duration"],
                        "published_at": item["snippet"]["publishedAt"]
                    }
            except Exception as e:
                logger.error(f"Erro ao buscar métricas do vídeo {video_id}: {e}")
        
        return {}
    
    def get_analytics_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Resumo de analytics do canal (usa dados da Data API).
        Para analytics completos, é necessário YouTube Analytics API com OAuth.
        """
        youtube = build(API_SERVICE_NAME, API_VERSION, developerKey=self.api_key)
        
        try:
            # Últimos vídeos
            response = youtube.search().list(
                part="snippet",
                channelId=self.channel_id,
                type="video",
                order="date",
                maxResults=10
            ).execute()
            
            videos = []
            total_views = 0
            for item in response.get("items", []):
                vid = item["snippet"]
                videos.append({
                    "title": vid["title"],
                    "video_id": item["id"]["videoId"],
                    "published": vid["publishedAt"]
                })
            
            # Busca métricas para cada vídeo
            video_ids = [v["video_id"] for v in videos]
            if video_ids:
                stats = youtube.videos().list(
                    part="statistics",
                    id=",".join(video_ids)
                ).execute()
                
                stats_map = {s["id"]: s["statistics"] for s in stats.get("items", [])}
                for v in videos:
                    s = stats_map.get(v["video_id"], {})
                    v["views"] = int(s.get("viewCount", 0))
                    v["likes"] = int(s.get("likeCount", 0))
                    total_views += v["views"]
            
            return {
                "data_consulta": datetime.datetime.now().isoformat(),
                "periodo_dias": days,
                "total_videos_analisados": len(videos),
                "total_views_periodo": total_views,
                "videos_recentes": videos
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar analytics: {e}")
            return {}
    
    def schedule_video(
        self,
        file_path: str,
        title: str,
        description: str,
        tags: List[str],
        publish_datetime: datetime.datetime,
        playlist_id: str = None
    ) -> Optional[Dict]:
        """Agenda um vídeo para publicação em data/hora específica."""
        return self.upload_video(
            file_path=file_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status="private",
            publish_at=publish_datetime,
            playlist_id=playlist_id
        )


def oauth_authenticate():
    """
    Executa autenticação OAuth2 interativa.
    Deve ser executado uma vez para gerar o token de acesso.
    """
    client_secrets = Path(__file__).parent.parent / "dados" / "youtube_client_secrets.json"
    
    if not client_secrets.exists():
        logger.error(f"Arquivo client_secrets.json não encontrado em {client_secrets}")
        logger.info("Baixe em: Google Cloud Console > APIs e Serviços > Credenciais > Criar Credenciais > OAuth Client ID > Aplicativo de área de trabalho")
        return None
    
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secrets),
        scopes=SCOPES
    )
    credentials = flow.run_local_server(port=0)
    
    # Salva token
    token_path = Path(__file__).parent.parent / "dados" / "youtube_token.json"
    import pickle
    with open(token_path, "wb") as f:
        pickle.dump(credentials, f)
    
    logger.info(f"Token salvo em {token_path}")
    return credentials


if __name__ == "__main__":
    # Teste rápido
    yt = YouTubeService()
    print("YouTube Service inicializado")
    print(f"Channel ID: {yt.channel_id}")
