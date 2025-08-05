"""Amis admin."""

from typing import Annotated, List
from fastapi import Depends, Request

from fastapi_amis_admin import admin
from fastapi_amis_admin.admin import AdminApp
from fastapi_amis_admin.amis import (
    Page,
    PageSchema,
    TableColumn,
    TableCRUD,
    TabsModeEnum,
)
from fastapi_amis_admin.crud.schema import (
    Paginator,
    BaseApiOut,
    ItemListSchema
)
from fastapi_amis_admin.models.fields import Field
from fastapi_amis_admin.utils.pydantic import (
    model_fields,
)
from pydantic import BaseModel

class ReDocsAdmin(admin.IframeAdmin):
    """IFrame for redocs."""
    page_schema = PageSchema(label="Docs", icon="fa fa-book")
    src = "/redoc"

    @classmethod
    def bind(cls, app: AdminApp) -> "ReDocsAdmin":
        app.register_admin(cls)
        return cls(app)

class BBCAdmin(admin.AdminApp):
    """BBC Admin."""
    page_schema = PageSchema(label="BBC iPlayer", icon="fa fa-tv", tabsMode=TabsModeEnum.radio)

    @classmethod
    def bind(cls, app: AdminApp) -> "BBCAdmin":
        app.register_admin(
            BBCCategoryAdmin,
            BBCProgrammeAdmin,
            BBCStreamAdmin,
        )
        return cls(app)


class BBCCategoryAdmin(admin.PageAdmin):
    page_schema = PageSchema(label="Categories", icon="fa fa-tv")
    paginator: Paginator = Paginator(perPageMax=100)

    class CategoryModel(BaseModel):
        category_id: str = Field(..., title="Category")
        total_pages: int = Field(..., title="Total Pages")

        @classmethod
        def parse_category(cls, category: str):
            from app.bbc import _CATEGORIES
            category_val = _CATEGORIES[category]
            return cls(category_id=category, total_pages=category_val["total_pages"])


    async def get_page(self, request: Request) -> Page:
        page = await super().get_page(request)
        headerToolbar = [
            "reload",
            "bulkActions",
            {"type": "pagination", "align": "right"},
            {
                "type": "tpl",
                "tpl": "SHOWING ${items|count} OF ${total} RESULT(S)",
                "className": "v-middle",
                "align": "right",
            },
        ]
        page.body = TableCRUD(
            api=f"get:{self.router_path}/categories",
            autoFillHeight=True,
            headerToolbar=headerToolbar,
            columns=await self.get_list_columns(request),
        )
        return page

    async def get_list_columns(self, request: Request) -> List[TableColumn]:
        columns = []
        for modelfield in model_fields(self.CategoryModel).values():
            column  = self.site.amis_parser.as_table_column(modelfield, False)
            if column:
                columns.append(column)
        return columns

    def register_router(self):
        """Register custom routes."""
        @self.router.get(
            "/categories",
            include_in_schema=False,
        )
        async def get_categories(paginator: Annotated[self.paginator, Depends()]):
            from app.bbc import _CATEGORIES
            start = (paginator.page - 1) * paginator.perPage
            end = paginator.page * paginator.perPage
            data = ItemListSchema(items=[self.CategoryModel.parse_category(category) for category in list(_CATEGORIES)[start:end]])
            data.total = len(_CATEGORIES) if paginator.show_total else None
            return BaseApiOut(data=data)

        return super().register_router()


class BBCProgrammeAdmin(admin.PageAdmin):
    page_schema = PageSchema(label="Programmes", icon="fa fa-tv")
    paginator: Paginator = Paginator(perPageMax=100)

    class ProgrammeModel(BaseModel):
        id: str = Field(..., title="ID")
        title: str = Field(..., title="Title")

        @classmethod
        def parse_programme(cls, programme: dict):
            return programme

    async def get_page(self, request: Request) -> Page:
        page = await super().get_page(request)
        headerToolbar = [
            "reload",
            "bulkActions",
            {"type": "pagination", "align": "right"},
            {
                "type": "tpl",
                "tpl": "SHOWING ${items|count} OF ${total} RESULT(S)",
                "className": "v-middle",
                "align": "right",
            },
        ]
        page.body = TableCRUD(
            api=f"get:{self.router_path}/programmes",
            autoFillHeight=True,
            headerToolbar=headerToolbar,
            filterTogglable=True,
            filterDefaultVisible=False,
            syncLocation=False,
            keepItemSelectionOnPageChange=True,
            footerToolbar=[
                "statistics",
                "switch-per-page",
                "pagination",
                "load-more",
                "export-csv",
            ],
            columns=await self.get_list_columns(request),
        )
        return page

    async def get_list_columns(self, request: Request) -> List[TableColumn]:
        columns = []
        for modelfield in model_fields(self.ProgrammeModel).values():
            column  = self.site.amis_parser.as_table_column(modelfield, False)
            if column:
                columns.append(column)
        return columns

    def register_router(self):
        """Register custom routes."""
        @self.router.get(
            "/programmes",
            include_in_schema=False,
        )
        def get_programmes(paginator: Annotated[self.paginator, Depends()]):
            from app.bbc import _PROGRAMMES
            start = (paginator.page - 1) * paginator.perPage
            end = paginator.page * paginator.perPage
            data = ItemListSchema(items=[programme for programme in _PROGRAMMES[start:end]])
            data.total = len(_PROGRAMMES)
            return BaseApiOut(data=data)

        return super().register_router()

class BBCStreamAdmin(admin.PageAdmin):
    page_schema = PageSchema(label="Streams", icon="fa fa-tv")
    paginator: Paginator = Paginator(perPageMax=100)

    async def get_page(self, request: Request) -> Page:
        page = await super().get_page(request)
        headerToolbar = [
            "reload",
            "bulkActions",
            {"type": "pagination", "align": "right"},
            {
                "type": "tpl",
                "tpl": "SHOWING ${items|count} OF ${total} RESULT(S)",
                "className": "v-middle",
                "align": "right",
            },
        ]
        page.body = TableCRUD(
            api=f"get:{self.router_path}/streams",
            autoFillHeight=True,
            headerToolbar=headerToolbar,
            filterTogglable=True,
            filterDefaultVisible=False,
            syncLocation=False,
            keepItemSelectionOnPageChange=True,
            footerToolbar=[
                "statistics",
                "switch-per-page",
                "pagination",
                "load-more",
                "export-csv",
            ],
            columns=await self.get_list_columns(request),
        )
        return page

    async def get_list_columns(self, request: Request) -> List[TableColumn]:
        columns = []
        return columns
    
    def register_router(self):
        """Register custom routes."""
        @self.router.get(
            "/streams",
            include_in_schema=False,
        )
        def get_streams(paginator: Annotated[self.paginator, Depends()]):
            from app.bbc import _STREAMS
            start = (paginator.page - 1) * paginator.perPage
            end = paginator.page * paginator.perPage
            data = ItemListSchema(items=[programme for programme in _STREAMS[start:end]])
            data.total = len(_STREAMS)
            return BaseApiOut(data=data)
