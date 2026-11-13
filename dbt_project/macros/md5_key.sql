{# Ma bam MD5 dang chuoi hex 32 ky tu #}
{% macro md5_key(expr) -%}
    md5(cast({{ expr }} as string))
{%- endmacro %}
