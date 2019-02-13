import base64
import json

import logging

from com.cognizant.devops.platformagents.core.BaseAgent import BaseAgent


class QtestAgent (BaseAgent):
    baseUrl, userName, password, startFrom, base64EncodeKey, bearerToken, apiHeaders, almEntities = [None] * 8

    def process(self):
        try:
            self.baseUrl = self.config.get('baseUrl', '')
            self.userName = self.config.get('username', '')
            self.password = self.config.get('password', '')
            self.startFrom = self.config.get('startFrom')
            self.pageSize = self.config.get('almEntityPageSize')
            encodeKey = 'InSightsAlmAgent:'
            self.base64EncodeKey = base64.b64encode(encodeKey.encode('utf-8'))
            token = self.login()
            self.bearerToken = 'bearer ' + token if token else None
            almEntities = {
                'defects': {
                    'api': '/defects/last-change',
                    'method': 'GET',
                    'param': '?startTime={0}&page={1}&pageSize={2}'
                },
                'test-cases': {
                    'api': '/search',
                    'method': 'POST',
                    'param': '?page={0}&pageSize={1}'
                }
            }
            # project API Call
            self.apiHeaders = {'Content-Type': 'application/json', 'accept': 'application/json', 'Authorization': self.bearerToken}
            projectList = self.getResponse(self.baseUrl+"/api/v3/projects?assigned=false", 'GET', None, None, None, None, self.apiHeaders)
            self.projectIter(projectList, almEntities)
        except Exception as err:
            logging.error(err)

    def projectIter(self, projectList, almEntities):
        try:
            for project in projectList:
                projectId = project.get('id', None)
                projectName = project.get('name', None)
                projectApiUrl = self.baseUrl + '/api/v3/projects/' + str(projectId)
                if projectId not in self.tracking:
                    self.tracking[projectId] = {}
                projectTrackingDetails = self.tracking[projectId]
                for entity in almEntities:
                    entityConfig = almEntities[entity]
                    entityUpdatedDate = self.startFrom if entity not in projectTrackingDetails else projectTrackingDetails['entityUpdatedDate']
                    nextResponse = True
                    page = 1
                    pageSize = self.pageSize
                    while nextResponse:
                        if entityConfig.get('method') == 'GET':
                            url = projectApiUrl + entityConfig.get('api') + entityConfig.get('param').format(entityUpdatedDate + 'Z', page, pageSize)
                            response = self.getResponse(url, 'GET', None, None, None, None, self.apiHeaders)
                            print response
                        elif entityConfig.get('method') == 'POST':
                            url = projectApiUrl + entityConfig.get('api') + entityConfig.get('param').format(page, pageSize)
                            payload = {'object_type': entity, 'fields': ['*'], 'query': '\'Last Modified Date\' >= \'{}\''.format(entityUpdatedDate + '+00:00')}
                            response = self.getResponse(url, 'POST', None, None, json.dumps(payload), None, self.apiHeaders)
                            print response
                        nextResponse = False
        except Exception as err:
            logging.error(err)

    def login(self):
        headers = {'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded', 'authorization': 'Basic ' + self.base64EncodeKey}
        payload = 'grant_type=password&username=' + self.userName + '&password=' + self.password
        response = self.getResponse(self.baseUrl + '/oauth/token', 'POST', None, None, payload, None, headers)
        if "error" in response:
            logging.error("InValid Credentails")
        return response.get("access_token", None)


if __name__ == '__main__':
    QtestAgent()
