use thiserror::Error;

pub type AppResult<T> = Result<T, AppError>;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("网络请求失败: {0}")]
    Http(#[from] reqwest::Error),
    #[error("文件操作失败: {0}")]
    Io(#[from] std::io::Error),
    #[error("数据格式无效: {0}")]
    Json(#[from] serde_json::Error),
    #[error("{0}")]
    Validation(String),
    #[error("{0}")]
    Protocol(String),
    #[error("密码加密数据无效")]
    Crypto,
}

impl From<AppError> for String {
    fn from(error: AppError) -> Self {
        error.to_string()
    }
}
