import base64
import json
import logging
from itertools import chain
from dateutil import parser

from com.cognizant.devops.platformagents.core.BaseAgent import BaseAgent


class QtestAgent (BaseAgent):
    baseUrl, userName, password, startFrom, base64EncodeKey, bearerToken, apiHeaders, almEntities, pageSize, historyEntities, entitySize = [None] * 11

    def process(self):
        try:
            self.baseUrl = self.config.get('baseUrl', '')
            self.userName = self.config.get('username', '')
            self.password = self.config.get('password', '')
            self.startFrom = self.config.get('startFrom')
            self.pageSize = self.config.get('almEntityPageSize')
            self.almEntityRestDetails()
            self.historyEntities = self.config.get('dynamicTemplate', {}).get('queryObjectHistory', {})
            self.entitySize = self.historyEntities.get('entitySize', 100)
            encodeKey = 'InSightsAlmAgent:'
            self.base64EncodeKey = base64.b64encode(encodeKey.encode('utf-8'))
            token = self.login()
            self.bearerToken = 'bearer ' + token if token else None
            # project API Call
            self.apiHeaders = {'Content-Type': 'application/json', 'accept': 'application/json', 'Authorization': self.bearerToken}
            projectList = self.getResponse(self.baseUrl+"/api/v3/projects?assigned=false", 'GET', None, None, None, None, self.apiHeaders)
            self.manipulatingProjectList(projectList)
        except Exception as err:
            logging.error(err)

    def manipulatingProjectList(self, projectList):
        try:
            for project in projectList:
                projectId = project.get('id', -1)
                projectName = project.get('name', '')
                projectApiUrl = self.baseUrl + '/api/v3/projects/' + str(projectId)
                if str(projectId) not in self.tracking:
                    self.tracking[str(projectId)] = dict()
                projectTrackingDetails = self.tracking[str(projectId)]
                for entity in self.almEntities:
                    toolsData = list()
                    entityConfig = self.almEntities[entity]
                    if entity not in projectTrackingDetails:
                        entityUpdatedDate = self.startFrom + '+00:00'
                        projectTrackingDetails[entity] = dict()
                    else:
                        entityUpdatedDate = projectTrackingDetails[entity]['entityUpdatedDate']
                    nextResponse, page, pageSize, payload = True, 1, self.pageSize, None
                    while nextResponse:
                        if entityConfig.get('method') == 'GET':
                            url = projectApiUrl + entityConfig.get('urlPattern').format(entityUpdatedDate + 'Z', page, pageSize)
                        else:
                            url = projectApiUrl + entityConfig.get('urlPattern').format(page, pageSize)
                            payload = entityConfig['payload'] % (entityUpdatedDate)
                        response = self.getResponse(url, entityConfig.get('method'), None, None, payload, None, self.apiHeaders)
                        entityTypeList = response.get('items', response.get('defects', [])) # if block
                        print entityTypeList
                        if len(entityTypeList) > 0:
                            injectData = {'projectId': projectId, 'projectName': projectName, 'almType': entity} # outside while
                            self.responseDataWrangling(entityConfig, entityTypeList, toolsData, injectData, entityUpdatedDate, projectTrackingDetails) # entl -> respDAtL, lastTrackiDate
                            page = page + 1
                        else:
                            nextResponse = False
                    if toolsData:
                        print toolsData
                        self.updateTrackingJson(self.tracking)
        except Exception as err:
            logging.error(err)

    def almEntityRestDetails(self):
        self.almEntities = {}
        native = {'defects': {'urlPattern': '/defects/last-change?startTime={0}&page={1}&size={2}', 'method': 'GET'}}
        search = {'urlPattern': '/search?page={0}&pageSize={1}', 'method': 'POST'}
        almEntitiesConfig = self.config.get('dynamicTemplate', {}).get('almEntities', {})
        exceptionProperty = ['apiType'] + self.config.get('exceptionProperty', [])
        for entity in almEntitiesConfig:
            entityConfig = almEntitiesConfig[entity]
            apiType = entityConfig.get('apiType', 'search')
            if apiType == 'native' and entity in native:
                self.almEntities[entity] = native[entity]
            else:
                self.almEntities[entity] = search.copy()
                self.almEntities[entity]['payload'] = json.dumps({'object_type': entity, 'fields': [field for field in entityConfig if field not in exceptionProperty], 'query': "'Last Modified Date' >= '%s'"})

    def responseDataWrangling(self, entityConfig, entityTypeList, toolsData, injectData, entityUpdatedDate, trackingDetails): # method name, entityConfig -> rTem
        entity = injectData['almType']
        lastModifiedDtStr = entityUpdatedDate
        lastModifiedDt = parser.parse(lastModifiedDtStr, ignoretz=True)
        entityObjectIdList = list()
        for entityObject in entityTypeList:
            entityLastModifiedDtStr = entityObject.get('last_modified_date', None)
            entityLastModifiedDt = parser.parse(entityLastModifiedDtStr, ignoretz=True)
            if entityLastModifiedDt > lastModifiedDt:
                lastModifiedDt = entityLastModifiedDt
                lastModifiedDtStr = entityLastModifiedDtStr
            entityObjectId = entityObject.get('id')
            entityObjectIdList.append(entityObjectId)
            if entityConfig:
                if injectData['almType'] == 'requirements':
                        injectData['jiraKey'] = entityObject.get('name', '').split(' ')[0]
                if entityObject.get('properties', []): # sep var
                    for entityProperty in entityObject.get('properties'):
                        injectData[str(entityProperty.get('field_name').lower()).replace(' ', '')] = entityProperty.get('field_value_name')
                toolsData += self.parseResponse(entityConfig, entityObject, injectData)
        trackingDetails[entity] = {'entityIdList': entityObjectIdList, 'entityUpdatedDate': lastModifiedDtStr}
        if entityObjectIdList and entity in self.historyEntities:
            print '*'*6, 'HistoryData', '*'*6
            print self.queryEarliestchangeHistoryStrategy(entityObjectIdList, **injectData)

    def login(self):
        headers = {'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded', 'authorization': 'Basic ' + self.base64EncodeKey}
        payload = 'grant_type=password&username=' + self.userName + '&password=' + self.password
        response = self.getResponse(self.baseUrl + '/oauth/token', 'POST', None, None, payload, None, headers)
        if "error" in response:
            logging.error(response)
        return response.get("access_token", None)

    def queryEarliestchangeHistoryStrategy(self, entityObjectIdList, **injectData): # method name
        try:
            toolsHistoryData = list()
            projectId = injectData.get('projectId')
            entity = injectData.get('almType')
            page = 1
            propertyLookUp = self.historyEntities.get(entity, {}).get("Type") # object var (-), entity -> t-c, process
            objectQueryChunks = self.constructHistoryObjectQuery(entityObjectIdList)
            for chunk in objectQueryChunks: # idChunk
                if chunk: # no need
                    nextResponse = True
                    while nextResponse:
                        historyResponse = self.queryObjectHistoryApi(projectId, entity, objectQuery=chunk, page=page, pageSize=self.pageSize) # include block here
                        if 'items' in historyResponse and historyResponse['items']:
                            changeHistoryList = historyResponse.get('items')
                            for changeHistory in changeHistoryList:
                                changesList = changeHistory['changes']
                                for changedField in changesList:
                                    if changedField['new_value'] == propertyLookUp['newValue']:
                                        data = {"projectId": projectId, "almType": entity, "id": changeHistory['linked_object']['object_id'],
                                                "automationTime": changeHistory['created']}
                                        toolsHistoryData.append(data)
                            page = page + 1
                        else:
                            nextResponse = False
            mappedHistoryData = self.mapToPair(toolsHistoryData)
            for entityObjectId in mappedHistoryData:
                mappedHistoryData[entityObjectId] = self.listSplitter(mappedHistoryData[entityObjectId], propertyLookUp.get('limit', 1))
            return list(chain.from_iterable(mappedHistoryData.values()))
        except Exception as err:
            logging.error(err)

    @staticmethod
    def mapToPair(historyDataList):
        try:
            # entityId to History Data Pair {entityId: [historyData]}
            idToHistoryPair = dict()
            for historyData in historyDataList:
                entityId = historyData['id']
                if entityId in idToHistoryPair:
                    idToHistoryPair.get(entityId).append(historyData)
                else:
                    idToHistoryPair[entityId] = [historyData, ]
            return idToHistoryPair
        except Exception as err:
            logging.error(err)

    @staticmethod
    def _ConstructHistoryObjectQuery(entityIdList):
        objectQuery = str()
        entityIdListLen = len(entityIdList)
        for index in range(0, entityIdListLen):
            entityId = entityIdList[index]
            objectQuery += '\'id\' = \'' + str(entityId) + '\''
            if index != entityIdListLen - 1:
                objectQuery += ' or '
        return objectQuery

    def constructHistoryObjectQuery(self, entityIdList):
        if len(entityIdList) > self.entitySize:
            objectQueryList = list()
            chunks = [entityIdList[_Iter: _Iter + self.entitySize] for _Iter in range(0, len(entityIdList), self.entitySize)] # expand
            for _Iter in chunks:
                objectQueryList.append(self._ConstructHistoryObjectQuery(_Iter))
            return objectQueryList
        else:
            return [self._ConstructHistoryObjectQuery(entityIdList), ]

    @staticmethod
    def listSplitter(dataList, limit=1, reverse=True):
        if reverse:
            limit = -limit
        return dataList[:limit] if limit >= 0 else dataList[limit:]

    def queryObjectHistoryApi(self, projectId, objectType, fields=None, objectQuery=None, query=None, page=None, pageSize=None):
        try:
            data = {"object_type": objectType, "fields": fields if fields else ["*"], "object_query": objectQuery if objectQuery else "", "query": query if query else ""}
            url = self.baseUrl + "/api/v3/projects/" + str(projectId) + ("/histories" if not page else "/histories?page={0}&pageSize={1}".format(page, pageSize))
            return self.getResponse(url, "POST", None, None, json.dumps(data), None, self.apiHeaders)
        except Exception as err:
            logging.error(err)


if __name__ == '__main__':
    QtestAgent()
