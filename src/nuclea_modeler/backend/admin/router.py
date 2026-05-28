"""Admin endpoints — operações administrativas pontuais.

Inclui o seed de schemas demo no Lakebase para usar como POC do app.
Esses endpoints requerem role ADMIN.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..._metadata import api_prefix
from ..core import Dependencies
from ..core.sql import SqlDependency
from ..lakebase.service import open_connection
from ..rbac.router import _current_email
from ..rbac.service import ROLE_ADMIN, require_role

router = APIRouter(prefix=f"{api_prefix}/admin", tags=["admin"])
log = logging.getLogger(__name__)


# ─── Demo schemas (Postgres DDL + dados) ──────────────────────────────────────
# Quatro modelos simples pra usar como POC do app. Cada bloco é um schema
# independente: DROP + CREATE SCHEMA + tabelas + FKs + alguns INSERTs.

_DEMO_SCHEMAS: dict[str, list[str]] = {
    "mercado": [
        "DROP SCHEMA IF EXISTS mercado CASCADE",
        "CREATE SCHEMA mercado",
        """CREATE TABLE mercado.categoria (
            categoria_id SERIAL PRIMARY KEY,
            nome VARCHAR(80) NOT NULL UNIQUE,
            descricao TEXT
        )""",
        """CREATE TABLE mercado.fornecedor (
            fornecedor_id SERIAL PRIMARY KEY,
            razao_social VARCHAR(160) NOT NULL,
            cnpj CHAR(14) UNIQUE,
            email VARCHAR(160),
            telefone VARCHAR(20)
        )""",
        """CREATE TABLE mercado.produto (
            produto_id SERIAL PRIMARY KEY,
            sku VARCHAR(32) NOT NULL UNIQUE,
            nome VARCHAR(160) NOT NULL,
            categoria_id INT NOT NULL REFERENCES mercado.categoria(categoria_id),
            fornecedor_id INT REFERENCES mercado.fornecedor(fornecedor_id),
            preco_unitario NUMERIC(10,2) NOT NULL,
            estoque_atual INT NOT NULL DEFAULT 0,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
        """CREATE TABLE mercado.movimentacao_estoque (
            movimentacao_id BIGSERIAL PRIMARY KEY,
            produto_id INT NOT NULL REFERENCES mercado.produto(produto_id),
            tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('ENTRADA','SAIDA')),
            quantidade INT NOT NULL,
            data_hora TIMESTAMPTZ NOT NULL DEFAULT now(),
            observacao TEXT
        )""",
        """INSERT INTO mercado.categoria (nome, descricao) VALUES
            ('Hortifruti','Frutas, legumes e verduras'),
            ('Padaria','Pães e doces'),
            ('Bebidas','Refrigerantes, água, sucos'),
            ('Limpeza','Produtos de limpeza doméstica')""",
        """INSERT INTO mercado.fornecedor (razao_social, cnpj, email) VALUES
            ('Cooperativa Verde Ltda','12345678000100','contato@verde.com.br'),
            ('Distribuidora Atlantica SA','98765432000111','vendas@atlantica.com.br')""",
        """INSERT INTO mercado.produto (sku, nome, categoria_id, fornecedor_id, preco_unitario, estoque_atual) VALUES
            ('SKU-001','Tomate Italiano (kg)',1,1,9.90,120),
            ('SKU-002','Pão Frances (un)',2,1,0.80,500),
            ('SKU-003','Refrigerante Cola 2L',3,2,9.50,80),
            ('SKU-004','Detergente Neutro 500ml',4,2,3.49,200)""",
    ],
    "musicas": [
        "DROP SCHEMA IF EXISTS musicas CASCADE",
        "CREATE SCHEMA musicas",
        """CREATE TABLE musicas.artista (
            artista_id SERIAL PRIMARY KEY,
            nome VARCHAR(160) NOT NULL,
            pais VARCHAR(80),
            ativo_desde INT,
            biografia TEXT
        )""",
        """CREATE TABLE musicas.genero (
            genero_id SERIAL PRIMARY KEY,
            nome VARCHAR(80) NOT NULL UNIQUE
        )""",
        """CREATE TABLE musicas.album (
            album_id SERIAL PRIMARY KEY,
            titulo VARCHAR(200) NOT NULL,
            artista_id INT NOT NULL REFERENCES musicas.artista(artista_id),
            genero_id INT REFERENCES musicas.genero(genero_id),
            ano_lancamento INT,
            duracao_total_min INT
        )""",
        """CREATE TABLE musicas.faixa (
            faixa_id BIGSERIAL PRIMARY KEY,
            album_id INT NOT NULL REFERENCES musicas.album(album_id),
            numero INT NOT NULL,
            titulo VARCHAR(200) NOT NULL,
            duracao_seg INT NOT NULL,
            UNIQUE (album_id, numero)
        )""",
        """INSERT INTO musicas.genero (nome) VALUES
            ('MPB'),('Rock'),('Pop'),('Sertanejo'),('Bossa Nova')""",
        """INSERT INTO musicas.artista (nome, pais, ativo_desde, biografia) VALUES
            ('Caetano Veloso','Brasil',1965,'Cantor e compositor baiano'),
            ('Tim Maia','Brasil',1968,'Pioneiro da soul brasileira'),
            ('The Beatles','Reino Unido',1960,'Banda inglesa lendária')""",
        """INSERT INTO musicas.album (titulo, artista_id, genero_id, ano_lancamento, duracao_total_min) VALUES
            ('Domingo',1,1,1971,38),
            ('Tim Maia 1972',2,1,1972,42),
            ('Abbey Road',3,2,1969,47)""",
        """INSERT INTO musicas.faixa (album_id, numero, titulo, duracao_seg) VALUES
            (1,1,'Domingo',197),
            (1,2,'Pra Ninguém',217),
            (2,1,'Não Quero Dinheiro',229),
            (2,2,'Réu Confesso',211),
            (3,1,'Come Together',259),
            (3,2,'Something',182)""",
    ],
    "livros": [
        "DROP SCHEMA IF EXISTS livros CASCADE",
        "CREATE SCHEMA livros",
        """CREATE TABLE livros.editora (
            editora_id SERIAL PRIMARY KEY,
            nome VARCHAR(160) NOT NULL UNIQUE,
            pais VARCHAR(80),
            fundada_em INT
        )""",
        """CREATE TABLE livros.autor (
            autor_id SERIAL PRIMARY KEY,
            nome VARCHAR(160) NOT NULL,
            nacionalidade VARCHAR(80),
            nascimento DATE
        )""",
        """CREATE TABLE livros.livro (
            livro_id SERIAL PRIMARY KEY,
            isbn VARCHAR(20) UNIQUE,
            titulo VARCHAR(240) NOT NULL,
            editora_id INT REFERENCES livros.editora(editora_id),
            ano_publicacao INT,
            paginas INT,
            sinopse TEXT
        )""",
        """CREATE TABLE livros.livro_autor (
            livro_id INT NOT NULL REFERENCES livros.livro(livro_id),
            autor_id INT NOT NULL REFERENCES livros.autor(autor_id),
            ordem INT,
            PRIMARY KEY (livro_id, autor_id)
        )""",
        """INSERT INTO livros.editora (nome, pais, fundada_em) VALUES
            ('Companhia das Letras','Brasil',1986),
            ('Penguin','Reino Unido',1935),
            ('Record','Brasil',1942)""",
        """INSERT INTO livros.autor (nome, nacionalidade, nascimento) VALUES
            ('Machado de Assis','Brasileira','1839-06-21'),
            ('Clarice Lispector','Brasileira','1920-12-10'),
            ('George Orwell','Britânica','1903-06-25')""",
        """INSERT INTO livros.livro (isbn, titulo, editora_id, ano_publicacao, paginas, sinopse) VALUES
            ('978-85-359-0277-5','Dom Casmurro',1,1899,256,'Romance clássico brasileiro'),
            ('978-85-209-1947-2','A Hora da Estrela',3,1977,96,'Última obra de Clarice'),
            ('978-0-452-28423-4','1984',2,1949,328,'Distopia política')""",
        """INSERT INTO livros.livro_autor (livro_id, autor_id, ordem) VALUES
            (1,1,1),(2,2,1),(3,3,1)""",
    ],
    "oficina": [
        "DROP SCHEMA IF EXISTS oficina CASCADE",
        "CREATE SCHEMA oficina",
        """CREATE TABLE oficina.cliente (
            cliente_id SERIAL PRIMARY KEY,
            nome VARCHAR(160) NOT NULL,
            cpf CHAR(11) UNIQUE,
            telefone VARCHAR(20),
            email VARCHAR(160),
            cadastrado_em TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
        """CREATE TABLE oficina.veiculo (
            veiculo_id SERIAL PRIMARY KEY,
            cliente_id INT NOT NULL REFERENCES oficina.cliente(cliente_id),
            placa CHAR(7) NOT NULL UNIQUE,
            marca VARCHAR(60) NOT NULL,
            modelo VARCHAR(80) NOT NULL,
            ano INT,
            km_atual INT
        )""",
        """CREATE TABLE oficina.servico (
            servico_id SERIAL PRIMARY KEY,
            descricao VARCHAR(200) NOT NULL,
            preco_base NUMERIC(10,2) NOT NULL
        )""",
        """CREATE TABLE oficina.ordem_servico (
            os_id SERIAL PRIMARY KEY,
            veiculo_id INT NOT NULL REFERENCES oficina.veiculo(veiculo_id),
            aberta_em TIMESTAMPTZ NOT NULL DEFAULT now(),
            fechada_em TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'ABERTA' CHECK (status IN ('ABERTA','EM_ANDAMENTO','FECHADA','CANCELADA')),
            valor_total NUMERIC(10,2)
        )""",
        """CREATE TABLE oficina.os_item (
            os_item_id BIGSERIAL PRIMARY KEY,
            os_id INT NOT NULL REFERENCES oficina.ordem_servico(os_id),
            servico_id INT NOT NULL REFERENCES oficina.servico(servico_id),
            quantidade INT NOT NULL DEFAULT 1,
            preco_unitario NUMERIC(10,2) NOT NULL
        )""",
        """INSERT INTO oficina.cliente (nome, cpf, telefone, email) VALUES
            ('Joana Silva','11122233344','11999990001','joana@example.com'),
            ('Carlos Souza','55566677788','11999990002','carlos@example.com')""",
        """INSERT INTO oficina.veiculo (cliente_id, placa, marca, modelo, ano, km_atual) VALUES
            (1,'ABC1D23','Honda','Civic',2018,82000),
            (2,'XYZ9K88','Toyota','Corolla',2020,45000)""",
        """INSERT INTO oficina.servico (descricao, preco_base) VALUES
            ('Troca de óleo',180.00),
            ('Alinhamento',120.00),
            ('Balanceamento',100.00),
            ('Revisão completa',650.00)""",
        """INSERT INTO oficina.ordem_servico (veiculo_id, valor_total) VALUES
            (1,300.00),(2,650.00)""",
        """INSERT INTO oficina.os_item (os_id, servico_id, quantidade, preco_unitario) VALUES
            (1,1,1,180.00),(1,2,1,120.00),(2,4,1,650.00)""",
    ],
}


@router.post("/seed-lakebase-demos", operation_id="seedLakebaseDemos")
def seed_lakebase_demos(
    sql: SqlDependency,
    user_ws: Dependencies.UserClient,
    app_ws: Dependencies.Client,
    instance_name: str = Query("JDBCTESTLAKEBASE", description="Lakebase instance name"),
    database: str = Query("databricks_postgres", description="Postgres database"),
    confirm: str = Query("", description="Pass confirm=yes para confirmar"),
) -> dict:
    """Cria 4 schemas demo (mercado, musicas, livros, oficina) no Lakebase
    Postgres, cada um com 3-5 tabelas, FKs e dados de exemplo.

    Idempotente — cada schema é dropado e recriado.

    Requer ADMIN role e confirm=yes (proteção contra cliques acidentais).
    """
    actor = _current_email(user_ws)
    require_role(sql, actor, ROLE_ADMIN)
    if confirm != "yes":
        raise HTTPException(400, "passe ?confirm=yes para confirmar o seed (vai DROPAR os schemas demo)")

    summary: dict[str, dict] = {}
    with open_connection(
        app_ws, instance_name=instance_name, database=database, user_email=None
    ) as conn:
        with conn.cursor() as cur:
            for schema_name, statements in _DEMO_SCHEMAS.items():
                applied = 0
                error: str | None = None
                try:
                    for stmt in statements:
                        cur.execute(stmt)
                        applied += 1
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)
                    log.warning(f"[seed-demos] schema={schema_name} stmt={applied + 1} erro: {error}")
                summary[schema_name] = {"statements_applied": applied, "error": error}

    return {
        "instance": instance_name,
        "database": database,
        "summary": summary,
    }
