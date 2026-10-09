# ShopWise: cadastro e login

Esta pasta contém a API usada pela interface. O cadastro de cliente e de supermercado usa `POST /api/auth/cadastro/`; o login usa `POST /api/auth/login/` e devolve um token e o tipo de conta.

Para testar no computador, deixe as pastas nesta estrutura:

```text
Projetos/
├── shopwise-api/
└── ShopWise/
    └── ShopWise/
```

Na pasta `shopwise-api`, prepare e inicie o servidor Django:

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py runserver
```

Abra `http://127.0.0.1:8000/static/src/pages/cadastrousuario.html` para cadastrar um cliente ou `http://127.0.0.1:8000/static/src/pages/cadastromercado.html` para cadastrar um supermercado. Depois entre pela página de login indicada. Use um e-mail diferente para cada conta; nomes de pessoas podem se repetir. A senha é obrigatória e pode ser simples.

Depois do login, o supermercado é levado a `manter-produtos.html`. Ali ele pode escolher um produto já existente ou criar um produto novo e cadastrar seu próprio preço e estoque. Cada supermercado edita ou remove apenas os dados da sua loja. A lista de produtos é compartilhada: dois mercados podem informar preços e estoques diferentes para o mesmo produto.

O formulário não pede foto. Produtos que já têm imagem no catálogo continuam mostrando essa imagem no estoque e no feed. Um produto novo sem imagem aparece sem foto; no feed, ele só aparece quando algum supermercado informar estoque disponível.

O envio de fotos pela API foi removido, incluindo a rota `/api/produtos/{id}/foto/` e o campo `foto`. As imagens existentes continuam no campo `imagem`, apontando para arquivos da interface.

A migração única `0001_shopwise` cria as tabelas atuais e cadastra os dez produtos ilustrados já com nomes simples, como Café, Leite e Feijão carioca. As imagens continuam na pasta `src/assets` da interface. Para colocar **alguns** produtos no estoque de Jorge Super e Quaresma, depois de cadastrar esses dois supermercados execute:

```powershell
.\venv\Scripts\python.exe manage.py popular_estoque_exemplo
```

Os preços e estoques de exemplo servem para a apresentação. O comando pode ser executado novamente: ele preserva preços e estoques já preenchidos pelos supermercados e completa apenas estoques antigos não informados.

O cliente entra em `feedproduto.html`. A página mostra apenas produtos com estoque maior que zero em pelo menos um supermercado, além de filtros por categoria e supermercado. O botão **Comparar preços** consulta `GET /api/produtos/{id}/comparar/` e lista apenas mercados com estoque disponível, do menor para o maior preço. O supermercado continua vendo seus itens sem estoque na tabela **Estoque Atual** para poder editá-los pelo botão **Editar**.

Para este fluxo, inicie o servidor desta pasta. A pasta da interface contém apenas as páginas e recursos visuais; o segundo projeto Django antigo foi removido.

## Comparação do carrinho

Na página `carrinho.html`, o botão **Comparar preços**, acima dos produtos, abre um popup com os produtos, a disponibilidade e o total em cada supermercado. A consulta considera as quantidades atuais do carrinho. O botão **Atualizar preços**, dentro do popup, refaz a comparação.

A rota pública `POST /api/carrinho/comparar/` recebe os produtos e suas quantidades:

```json
{
  "itens": [
    { "produto": 1, "quantidade": 2 },
    { "produto": 8, "quantidade": 1 }
  ]
}
```

Os IDs são exemplos; consulte `GET /api/produtos/` para obter os IDs do catálogo. Quantidades devem ser inteiros positivos. Se o mesmo produto aparecer mais de uma vez, suas quantidades são somadas antes da consulta de estoque.

A resposta contém `menor_total` e uma lista de `supermercados`, com o total, os preços de cada item e a disponibilidade. Os valores monetários são strings com duas casas decimais. Somente mercados com todos os produtos e estoque suficiente recebem um `total`; nos demais, `completo` é falso e `total` é nulo. A economia compara apenas os totais completos. Entrega, cupons e cashback não entram nesse cálculo.

Esse endpoint calcula a comparação; ele não reserva estoque nem cria pedidos. Não exige alterações no banco de dados.

## Compra e pedidos

Execute `manage.py migrate` para preparar as tabelas. No popup do carrinho, **Comprar neste supermercado** fica disponível apenas nos mercados com todos os itens e estoque suficiente. O checkout usa os preços do mercado selecionado e exige login de cliente. A taxa de entrega é R$ 5,00; retirada é gratuita. SHOPWISE10 e ECONOMIA5 dão desconto sobre os produtos. O pagamento continua demonstrativo, sem cobrança online e sem enviar dados de cartão à API.

Rotas autenticadas por `Authorization: Token SEU_TOKEN`, implementadas com `APIView`:

| Método e rota | Função |
| --- | --- |
| `POST /api/pedidos/` | Confirmar compra e descontar estoque |
| `GET /api/pedidos/` | Listar pedidos da conta |
| `GET /api/pedidos/{id}/` | Consultar detalhes |
| `PATCH /api/pedidos/{id}/` | Atualizar status pelo supermercado responsável |

Exemplo de confirmação (use IDs e total do seu carrinho):

```json
{
  "supermercado": 1,
  "itens": [{"produto": 1, "quantidade": 2}],
  "total_esperado": "19.78",
  "chave": "cddc99a4-e2a6-4de8-9bf6-d3e9a1c69d8c",
  "recebimento": "pickup",
  "pagamento": "entrega",
  "endereco": "",
  "observacoes": "",
  "cupom": ""
}
```

A interface gera a chave automaticamente e a mantém nas tentativas repetidas da mesma confirmação, evitando pedido duplicado. A API calcula os valores atuais, valida todo o estoque e salva pedido, itens e baixa de estoque na mesma transação. Se o total mudou ou faltou estoque, devolve `409` sem registrar a compra. O checkout atualiza os valores e pede nova confirmação. Os nomes e preços dos itens são guardados no pedido para preservar o histórico.

Clientes veem apenas suas compras; supermercados veem apenas os pedidos recebidos por suas lojas. Administradores podem consultar todos. Na página `pedidos.html`, o responsável avança o status com **Iniciar preparação** e **Concluir pedido**. A sequência é `recebido` → `em_preparacao` → `concluido`; o cliente acompanha pelos três grupos e pelo popup de detalhes. A lista pode ser atualizada manualmente e é consultada a cada 30 segundos enquanto a página está visível.

Para verificar a API: `.\venv\Scripts\python.exe manage.py test produtos --noinput`.

## Migrações consolidadas

As migrações antigas de produtos (`0001` a `0011`) foram substituídas por `produtos/migrations/0001_shopwise.py`. Esse arquivo mantém a informação de quais migrações substitui para reconhecer bancos já atualizados. Instalações novas usam apenas esse arquivo e já recebem o catálogo com nomes simples, sem o campo de upload de fotos.

Para colegas com banco antigo: antes de atualizar para esta versão, execute `manage.py migrate` na versão anterior, com as migrações até `0011`, e guarde uma cópia de `db.sqlite3`. Depois atualize o código e execute `manage.py migrate` novamente. Bancos com apenas parte das migrações antigas aplicadas precisam concluir essa atualização na versão anterior primeiro. Não apague o banco para corrigir conflitos de migração.
