"""Conservative OpenAPI 3 JSON importer: reviewed drafts, never auto-execute."""
import re


def import_openapi(spec, base_url):
    if not isinstance(spec, dict) or not str(spec.get('openapi','')).startswith('3.'):
        raise ValueError('请导入 OpenAPI 3.x JSON 文档')
    if not isinstance(spec.get('paths'), dict):
        raise ValueError('接口文档缺少 paths')
    tools, warnings = [], []
    paths = spec['paths']
    for path, entry in paths.items():
        if not isinstance(entry, dict):
            continue
        for method, operation in entry.items():
            if method not in ('get','post'):
                if method in ('put','patch','delete'):
                    warnings.append(f'{method.upper()} {path}：本版不支持')
                continue
            if '{' in path or not isinstance(operation,dict) or '$ref' in operation:
                warnings.append(f'{method.upper()} {path}：暂不支持参数路径或引用')
                continue
            props, required = {}, []
            params = entry.get('parameters',[]) + operation.get('parameters',[])
            unsupported = False
            for parameter in params:
                if not isinstance(parameter,dict) or parameter.get('in')!='query' or parameter.get('schema',{}).get('type')!='string':
                    unsupported=True
                    break
                name=parameter.get('name')
                if not isinstance(name,str):
                    unsupported=True
                    break
                props[name]=parameter['schema']
                if parameter.get('required'):
                    required.append(name)
            if unsupported or (method=='post' and props):
                warnings.append(f'{method.upper()} {path}：仅支持字符串查询参数或 JSON 请求体，不能混用')
                continue
            if method=='post':
                schema=operation.get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema',{})
                if schema.get('type')!='object' or '$ref' in schema or any(p.get('type')!='string' or '$ref' in p for p in schema.get('properties',{}).values()):
                    warnings.append(f'POST {path}：仅支持内联对象与字符串字段')
                    continue
                props=schema.get('properties',{})
                required=schema.get('required',[])
                if 'get' not in paths.get(path+'/{id}',{}):
                    warnings.append(f'POST {path}：未找到 GET {path}/{{id}} 回查接口，跳过')
                    continue
            name=operation.get('operationId') or (method+'_'+path.strip('/').replace('/','_'))
            name=re.sub(r'[^a-zA-Z0-9_]','_',name)
            if not name or not name[0].isalpha():
                name='api_'+name
            tool={'name':name[:64],'description':operation.get('description') or operation.get('summary') or method.upper()+' '+path,'base_url':base_url,'path':path,'method':method.upper(),'parameters':{'type':'object','properties':props,'required':required,'additionalProperties':False}}
            if method=='post':
                tool['verify_path']=path+'/{id}'
            tools.append(tool)
    return {'tools':tools,'warnings':warnings,'note':'这是待审核草稿。确认路径、业务含义、授权和回查格式后再保存；不兼容接口会明确跳过。'}
