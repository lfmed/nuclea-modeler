-- =====================================================
-- SCHEMA
-- =====================================================
CREATE SCHEMA streaming;
SET search_path TO streaming;

-- =====================================================
-- CLASSIFICAÇÃO INDICATIVA
-- =====================================================
CREATE TABLE classificacao_indicativa (
    id_classificacao SERIAL PRIMARY KEY,
    codigo VARCHAR(10) UNIQUE NOT NULL,
    descricao TEXT
);

-- =====================================================
-- GENERO
-- =====================================================
CREATE TABLE genero (
    id_genero SERIAL PRIMARY KEY,
    nome VARCHAR(100) UNIQUE NOT NULL
);

-- =====================================================
-- TIPO CONTEUDO
-- =====================================================
CREATE TABLE tipo_conteudo (
    id_tipo SERIAL PRIMARY KEY,
    nome VARCHAR(50) UNIQUE NOT NULL
);

-- =====================================================
-- PESSOA
-- =====================================================
CREATE TABLE pessoa (
    id_pessoa SERIAL PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    data_nascimento DATE,
    nacionalidade VARCHAR(100)
);

-- =====================================================
-- CONTEUDO (BASE)
-- =====================================================
CREATE TABLE conteudo (
    id_conteudo SERIAL PRIMARY KEY,
    titulo VARCHAR(255) NOT NULL,
    descricao TEXT,
    ano_lancamento INT CHECK (ano_lancamento >= 1900),
    duracao_minutos INT,
    id_classificacao INT,
    id_tipo INT NOT NULL,

    FOREIGN KEY (id_classificacao) REFERENCES classificacao_indicativa(id_classificacao),
    FOREIGN KEY (id_tipo) REFERENCES tipo_conteudo(id_tipo)
);

-- =====================================================
-- SERIES (HERANÇA LOGICA)
-- =====================================================
CREATE TABLE serie (
    id_conteudo INT PRIMARY KEY,
    numero_temporadas INT,
    status VARCHAR(50),

    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo) ON DELETE CASCADE
);

-- =====================================================
-- TEMPORADA / EPISÓDIO
-- =====================================================
CREATE TABLE temporada (
    id_temporada SERIAL PRIMARY KEY,
    id_conteudo INT,
    numero_temporada INT,
    ano_lancamento INT,

    FOREIGN KEY (id_conteudo) REFERENCES serie(id_conteudo) ON DELETE CASCADE
);

CREATE TABLE episodio (
    id_episodio SERIAL PRIMARY KEY,
    id_temporada INT,
    numero_episodio INT,
    titulo VARCHAR(255),
    duracao_minutos INT,

    FOREIGN KEY (id_temporada) REFERENCES temporada(id_temporada) ON DELETE CASCADE
);

-- =====================================================
-- RELACIONAMENTOS N:N
-- =====================================================
CREATE TABLE conteudo_genero (
    id_conteudo INT,
    id_genero INT,
    PRIMARY KEY (id_conteudo, id_genero),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo) ON DELETE CASCADE,
    FOREIGN KEY (id_genero) REFERENCES genero(id_genero)
);

CREATE TABLE elenco (
    id_conteudo INT,
    id_pessoa INT,
    personagem VARCHAR(255),
    PRIMARY KEY (id_conteudo, id_pessoa),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo),
    FOREIGN KEY (id_pessoa) REFERENCES pessoa(id_pessoa)
);

CREATE TABLE direcao (
    id_conteudo INT,
    id_pessoa INT,
    PRIMARY KEY (id_conteudo, id_pessoa),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo),
    FOREIGN KEY (id_pessoa) REFERENCES pessoa(id_pessoa)
);

-- =====================================================
-- IDIOMA
-- =====================================================
CREATE TABLE idioma (
    id_idioma SERIAL PRIMARY KEY,
    nome VARCHAR(100) UNIQUE
);

CREATE TABLE conteudo_idioma (
    id_conteudo INT,
    id_idioma INT,
    tipo VARCHAR(20) CHECK (tipo IN ('AUDIO','LEGENDA')),
    PRIMARY KEY (id_conteudo, id_idioma, tipo),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo),
    FOREIGN KEY (id_idioma) REFERENCES idioma(id_idioma)
);

-- =====================================================
-- PRODUTORA / PREMIO
-- =====================================================
CREATE TABLE produtora (
    id_produtora SERIAL PRIMARY KEY,
    nome VARCHAR(255)
);

CREATE TABLE conteudo_produtora (
    id_conteudo INT,
    id_produtora INT,
    PRIMARY KEY (id_conteudo, id_produtora),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo),
    FOREIGN KEY (id_produtora) REFERENCES produtora(id_produtora)
);

CREATE TABLE premio (
    id_premio SERIAL PRIMARY KEY,
    nome VARCHAR(255),
    ano INT
);

CREATE TABLE conteudo_premio (
    id_conteudo INT,
    id_premio INT,
    PRIMARY KEY (id_conteudo, id_premio),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo),
    FOREIGN KEY (id_premio) REFERENCES premio(id_premio)
);

-- =====================================================
-- USUARIOS / PERFIS
-- =====================================================
CREATE TABLE usuario (
    id_usuario SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    pais_origem VARCHAR(100),
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE perfil (
    id_perfil SERIAL PRIMARY KEY,
    id_usuario INT,
    nome VARCHAR(100),
    idioma_preferido INT,
    classificacao_maxima INT,

    FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario) ON DELETE CASCADE,
    FOREIGN KEY (idioma_preferido) REFERENCES idioma(id_idioma),
    FOREIGN KEY (classificacao_maxima) REFERENCES classificacao_indicativa(id_classificacao)
);

-- =====================================================
-- DISPONIBILIDADE GLOBAL
-- =====================================================
CREATE TABLE pais (
    id_pais SERIAL PRIMARY KEY,
    nome VARCHAR(100)
);

CREATE TABLE disponibilidade_conteudo (
    id_conteudo INT,
    id_pais INT,
    data_inicio DATE,
    data_fim DATE,
    PRIMARY KEY (id_conteudo, id_pais),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo),
    FOREIGN KEY (id_pais) REFERENCES pais(id_pais)
);

-- =====================================================
-- QUALIDADE
-- =====================================================
CREATE TABLE qualidade_video (
    id_qualidade SERIAL PRIMARY KEY,
    nome VARCHAR(50)
);

CREATE TABLE conteudo_qualidade (
    id_conteudo INT,
    id_qualidade INT,
    PRIMARY KEY (id_conteudo, id_qualidade),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo),
    FOREIGN KEY (id_qualidade) REFERENCES qualidade_video(id_qualidade)
);

-- =====================================================
-- TAGS (ALGORITMOS)
-- =====================================================
CREATE TABLE tag (
    id_tag SERIAL PRIMARY KEY,
    nome VARCHAR(100) UNIQUE
);

CREATE TABLE conteudo_tag (
    id_conteudo INT,
    id_tag INT,
    relevancia NUMERIC(3,2),
    PRIMARY KEY (id_conteudo, id_tag),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo),
    FOREIGN KEY (id_tag) REFERENCES tag(id_tag)
);

-- =====================================================
-- HISTÓRICO
-- =====================================================
CREATE TABLE historico_visualizacao (
    id_historico SERIAL PRIMARY KEY,
    id_perfil INT,
    id_conteudo INT,
    progresso_segundos INT,
    assistido BOOLEAN,
    data_visualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_perfil) REFERENCES perfil(id_perfil),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo)
);

-- CONTINUAR ASSISTINDO
CREATE TABLE continuar_assistindo (
    id_perfil INT,
    id_conteudo INT,
    progresso_segundos INT,
    ultima_interacao TIMESTAMP,
    PRIMARY KEY (id_perfil, id_conteudo),
    FOREIGN KEY (id_perfil) REFERENCES perfil(id_perfil),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo)
);

-- FAVORITOS
CREATE TABLE lista_usuario (
    id_perfil INT,
    id_conteudo INT,
    data_adicao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_perfil, id_conteudo),
    FOREIGN KEY (id_perfil) REFERENCES perfil(id_perfil),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo)
);

-- =====================================================
-- AVALIAÇÕES
-- =====================================================
CREATE TABLE avaliacao_usuario (
    id_perfil INT,
    id_conteudo INT,
    gostei BOOLEAN,
    nota NUMERIC(2,1),
    PRIMARY KEY (id_perfil, id_conteudo),
    FOREIGN KEY (id_perfil) REFERENCES perfil(id_perfil),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo)
);

-- =====================================================
-- MÉTRICAS / TRENDING
-- =====================================================
CREATE TABLE metrica_conteudo (
    id_conteudo INT PRIMARY KEY,
    total_visualizacoes BIGINT DEFAULT 0,
    total_completos BIGINT DEFAULT 0,
    score_popularidade NUMERIC(10,2),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo)
);

CREATE TABLE trending_conteudo (
    id_conteudo INT,
    data_referencia DATE,
    posicao INT,
    PRIMARY KEY (id_conteudo, data_referencia),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo)
);

-- =====================================================
-- RECOMENDAÇÕES
-- =====================================================
CREATE TABLE recomendacao (
    id_recomendacao SERIAL PRIMARY KEY,
    id_perfil INT,
    id_conteudo INT,
    score NUMERIC(5,4),
    motivo TEXT,
    FOREIGN KEY (id_perfil) REFERENCES perfil(id_perfil),
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo)
);

-- =====================================================
-- MIDIA
-- =====================================================
CREATE TABLE midia (
    id_midia SERIAL PRIMARY KEY,
    id_conteudo INT,
    tipo VARCHAR(50),
    url TEXT,
    FOREIGN KEY (id_conteudo) REFERENCES conteudo(id_conteudo)
);

-- =====================================================
-- RELAÇÕES ENTRE CONTEÚDOS
-- =====================================================
CREATE TABLE conteudo_relacionado (
    id_conteudo_origem INT,
    id_conteudo_destino INT,
    tipo_relacao VARCHAR(50),
    PRIMARY KEY (id_conteudo_origem, id_conteudo_destino),
    FOREIGN KEY (id_conteudo_origem) REFERENCES conteudo(id_conteudo),
    FOREIGN KEY (id_conteudo_destino) REFERENCES conteudo(id_conteudo)
);
``